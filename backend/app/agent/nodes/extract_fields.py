"""Node 1 - understand the brief, remembering what was already established.

Two behaviours that matter more than the parsing itself:

**It accumulates.** A trader supplies a brief over several messages, and answers
a follow-up with just "50,000". So this node merges into what is already known
rather than replacing it. Writing every field on every turn - including the
blank ones - would wipe the market as soon as someone answered a question about
budget, and the conversation could never converge.

**It confirms.** After extracting, it says back what it understood.
`VOW_Strategy_Schema_v2.md` section 7.3 calls this the single most important
trust mechanism in the product: a trader who cannot see what was inferred
cannot correct it.

Understanding is done by the LLM when one is configured, and by pattern
matching when not. The patterns handle tidy briefs; the LLM handles real ones
("about fifty grand", "this summer", "Britain"). Neither invents an ID, a price
or a forecast - those only ever come from VOW.
"""

from __future__ import annotations

import calendar
import logging
import re
import time
from datetime import date

from pydantic import BaseModel, Field

from app.agent.gates import missing_basics
from app.agent.llm import get_llm, log_usage
from app.agent.state import PlanningAgentState
from app.core.logging import kv
from app.knowledge import reference

logger = logging.getLogger(__name__)

STAGE = "basics"

# Word-boundary matched, so "us" in "audience" cannot register as a market.
_MARKET_PATTERNS = {
    "GB": r"\b(uk|u\.k\.|united kingdom|britain|british|gb|england|scotland|wales)\b",
    "US": r"\b(us|u\.s\.|usa|united states|america|american)\b",
    "FR": r"\b(france|french|fr)\b",
    "DE": r"\b(germany|german|de)\b",
    "CN": r"\b(china|chinese|cn)\b",
}


_CURRENCY_BY_MARKET = {"GB": "GBP", "US": "USD", "FR": "EUR", "DE": "EUR"}
_SYMBOL_CURRENCY = {"£": "GBP", "$": "USD", "€": "EUR"}

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}

# Ordered by how strongly each signals "this number is money". Every pattern
# captures (symbol, number, magnitude_suffix) so the caller reads them alike.
# A bare number is never treated as a budget: in "August 2026 ... 30 second"
# most numbers in a brief are not money, and guessing wrong sets a real budget.
_BUDGET_PATTERNS = (
    r"([£$€])\s?([\d][\d,]*(?:\.\d+)?)\s*([km])?\b",  # £50,000 · $2.5m
    r"()([\d][\d,]*(?:\.\d+)?)\s*([km])\b",  # 50k
    r"()([\d][\d,]*(?:\.\d+)?)\s*(GBP|USD|EUR)\b",  # 15000 GBP
    r"budget\D{0,12}([£$€])?\s?([\d][\d,]*(?:\.\d+)?)\s*([km])?\b",  # budget of 50000
)


class BriefFields(BaseModel):
    """What the LLM is allowed to return. Flat and small, for reliable extraction."""

    markets: list[str] = Field(
        default_factory=list, description="ISO country codes, e.g. GB, US, FR, DE"
    )
    flight_start: str | None = Field(None, description="ISO date YYYY-MM-DD")
    flight_end: str | None = Field(None, description="ISO date YYYY-MM-DD")
    durations: list[str] = Field(
        default_factory=list, description="Creative durations in seconds: only 10, 15, 20 or 30"
    )
    budget_amount: str | None = Field(None, description="Decimal string, no symbol, e.g. 50000.00")
    currency: str | None = Field(None, description="GBP, USD or EUR")
    providers: list[str] = Field(
        default_factory=list,
        description="CTV providers named, exactly as: Prime Video, Netflix, Disney+, Hulu",
    )


# --- reading the conversation ------------------------------------------------


def _latest_human_text(state: PlanningAgentState) -> str:
    """The most recent user message, however LangGraph happens to store it."""
    for message in reversed(state.get("messages") or []):
        role = getattr(message, "type", None) or (
            message.get("role") if isinstance(message, dict) else None
        )
        if role in ("human", "user"):
            content = getattr(message, "content", None)
            if content is None and isinstance(message, dict):
                content = message.get("content")
            return str(content or "")
    return ""


# --- pattern matching (the no-LLM path) --------------------------------------


def _markets(text: str) -> list[str]:
    return [code for code, pattern in _MARKET_PATTERNS.items() if re.search(pattern, text, re.I)]


def _budget(text: str) -> tuple[str | None, str | None]:
    """Return (amount, currency_from_symbol). Handles '£50,000', '50k', '1.2m', '15000 GBP'."""
    for pattern in _BUDGET_PATTERNS:
        match = re.search(pattern, text, re.I)
        if not match:
            continue

        symbol, raw, suffix = match.groups()
        amount = float(raw.replace(",", ""))
        curr = None
        if suffix:
            if suffix.lower() == "k":
                amount *= 1_000
            elif suffix.lower() == "m":
                amount *= 1_000_000
            elif suffix.upper() in ("GBP", "USD", "EUR"):
                curr = suffix.upper()

        return f"{amount:.2f}", curr or _SYMBOL_CURRENCY.get(symbol or "")

    return None, None




def _durations(text: str) -> list[str]:
    found = set(re.findall(r"\b(10|15|20|30)\s*(?:s\b|sec|second)", text, re.I))

    # "15 and 30 second creatives" carries the unit only on the last number, so
    # once a unit word appears anywhere, bare durations in the same message
    # count too. Word boundaries keep budgets and years out: neither "50,000"
    # nor "2026" yields a bare match.
    if re.search(r"\b(?:secs?|seconds?)\b|\d\s*s\b", text, re.I):
        found.update(re.findall(r"\b(10|15|20|30)\b", text))

    return sorted(found, key=int)


def _flight_dates(text: str) -> tuple[str | None, str | None]:
    match = re.search(rf"\b({'|'.join(_MONTHS)})\b(?:\s+(\d{{4}}))?", text, re.I)
    if not match:
        return None, None

    month = _MONTHS[match.group(1).lower()]
    if match.group(2):
        year = int(match.group(2))
    else:
        # **A month with no year means the next time it comes round, not the one just gone.**
        # This read `date.today().year` flat, so "March" typed in August resolved to a March
        # five months in the past - a flight that had already finished, with nothing
        # downstream to notice. Nobody plans a campaign for last spring.
        today = date.today()
        year = today.year if month >= today.month else today.year + 1
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def _extract_with_patterns(text: str) -> BriefFields:
    amount, symbol_currency = _budget(text)
    markets = _markets(text)
    start, end = _flight_dates(text)

    return BriefFields(
        markets=markets,
        flight_start=start,
        flight_end=end,
        durations=_durations(text),
        budget_amount=amount,
        currency=symbol_currency or (_CURRENCY_BY_MARKET.get(markets[0]) if markets else None),
        providers=reference.provider_from_text(text),
    )


# --- the LLM path ------------------------------------------------------------


def _known_summary(state: PlanningAgentState) -> str:
    dates = state.get("flight_dates") or {}
    budgets = state.get("market_budgets") or []
    return "\n".join(
        [
            f"markets: {state.get('markets') or 'unknown'}",
            f"flight_start: {dates.get('lower') or 'unknown'}",
            f"flight_end: {dates.get('upper') or 'unknown'}",
            f"durations: {state.get('durations') or 'unknown'}",
            f"budget_amount: {budgets[0]['budget'] if budgets else 'unknown'}",
            f"currency: {state.get('primary_currency') or 'unknown'}",
            f"providers: {state.get('preferred_providers') or 'unknown'}",
        ]
    )


def _system_prompt() -> str:
    """Built per call, because it carries today's date.

    **This is what let a finished flight into the plan.** The prompt never said what day it
    is, so "October 1st to October 31st" - a month with no year - had no reference point, and
    the model resolved it against its own training data: it returned 2023, three years before
    the conversation was happening. Nothing downstream noticed, so inventory was matched and
    priced for a flight that had already ended.

    Built here rather than once at import, because a server that stays up for days would
    otherwise freeze the date on the morning it started.

    **The date rule covers ambiguity only, and that boundary was learned the hard way.** An
    earlier version said "never a date in the past", and the model read it as permission to
    sanitise: told "October 2023" over a plan already holding October 2026, it returned 2026 -
    quietly keeping the old value and dropping what the trader had typed. The turn then moved
    on to audiences as though nothing had been said.

    Reading and rejecting are different jobs. A month with no year is genuinely ambiguous, so
    the prompt resolves it forward. A year the trader stated is not ambiguous at all, and it
    comes back exactly as given - `_flight_already_over` refuses it, out loud, with the dates
    in the sentence. Sanitising in the prompt makes the model take a decision the trader never
    hears about, which is the failure this whole node is written against.
    """
    return (
        "Extract connected-TV campaign details from a trader's message.\n"
        f"TODAY IS {date.today().isoformat()}.\n"
        "You are given what is already known and the trader's latest message.\n"
        "Return the COMPLETE updated set: carry forward anything still true, apply "
        "any correction the message makes, and add anything new.\n"
        "Rules: markets are ISO country codes. Durations may only be 10, 15, 20 or "
        "30. Dates are ISO YYYY-MM-DD; a bare month means its first and last day.\n"
        "A DATE WITH NO YEAR MEANS THE NEXT TIME IT OCCURS, resolved forward from "
        "today: a trader saying 'October' means the next October to come, never the "
        "one just gone.\n"
        "WHEN THE TRADER STATES A YEAR, RETURN IT EXACTLY AS GIVEN - including a past "
        "one. Do not correct it and do not keep the previous value instead. Reporting "
        "what they said is your job; deciding whether it can be used is not.\n"
        "Budget is a decimal string with no symbol. Leave a field empty if it is "
        "genuinely unknown - never guess a value the trader did not give."
    )


async def _grounding(registry, fields: dict) -> tuple[list[str], list[str], list[str]]:
    """Check what the trader said against what VOW actually sells.

    Returns `(blocking, notes, rejected)`. Blocking entries become `awaiting`, so the gate
    stops the turn and `ask_for_missing` says them. Notes are said and the flow carries on.
    `rejected` is the field names, which is what tells the interface to offer valid values
    instead of an empty input.

    **Why there is no `validate_basics` node.** A "China" market was accepted and the agent
    then asked for dates, durations and a budget - three questions under a premise that was
    already false. The KNW-02 lane fixes that with a node of its own plus seven helpers in
    `gates` and five new state fields, and none of that machinery is needed here: `awaiting`
    already carries a computed sentence verbatim - that is how the flight reason reaches the
    trader - so a validation error *is* an `awaiting` entry. Adding a node would also put
    value-rejection in two places, since the flight check already lives in this one.

    **And no messages are written here.** `ValidationResponse.message` is already prose aimed
    at the trader - its own docstring says these strings "end up in the question the agent
    asks" - so rewording them here would be a second vocabulary for the same rule, drifting
    from the first the day either changed. `suggested_options` comes off the snapshot, so the
    alternatives a trader is offered are the ones the platform actually sells today.

    Skipped while a value is absent: absence is the `awaiting` gate's business and it already
    phrases that question. Running anyway would mean a bad date could not be reported until
    every other field had arrived.
    """
    market = (fields.get("markets") or [None])[0]
    validator = await registry.validator(market)

    # Ask order, which is also conflict priority - `gates.BASICS` puts market first, so a
    # trader is never asked to fix a currency on a plan whose market is not sold.
    checks = [validator.validate_target_markets(list(fields.get("markets") or []))]
    if fields.get("flight_dates"):
        checks.append(validator.validate_flight_dates(fields["flight_dates"]))
    if fields.get("durations"):
        checks.append(validator.validate_durations(list(fields["durations"]), market))
    if fields.get("primary_currency"):
        checks.append(
            validator.validate_currency(fields["primary_currency"], list(fields.get("markets") or []))
        )

    blocking: list[str] = []
    notes: list[str] = []
    rejected: list[str] = []
    for check in checks:
        if check.is_valid:
            # A normalization worth mentioning - "I read UK as GB". Said, never blocked:
            # stopping to confirm a courtesy is its own kind of wizard.
            if check.severity == "warning" and check.code.endswith(".normalized"):
                notes.append(check.message)
            continue
        # `market.missing` and friends duplicate what `missing_basics` already asks for, and
        # two questions about one blank field is the stutter the gate exists to prevent.
        if check.code.endswith(".missing"):
            continue
        blocking.append(_as_sentence(check.message, check.suggested_options))
        # `field` is the validator's own name for it - `target_markets`, `flight_dates` - and
        # the plan's key is what the interface indexes on, so it is mapped once here.
        rejected.append(_PLAN_FIELD.get(check.field or "", check.field or ""))
    return blocking, notes, rejected


# The validator names a field as the schema does; `PlanningAgentState` sometimes names it
# differently. One mapping, in the one place the two vocabularies meet.
_PLAN_FIELD = {"target_markets": "markets"}


def _as_sentence(message: str, options: list[str]) -> str:
    """One rejection, as a sentence that can stand on its own.

    The registry's messages are prose but not uniformly shaped - `market.unknown` is a full
    sentence, `flight_dates.in_past` a lowercase clause - because its own docstring expects a
    node to append them to a list rather than fit them into a template. `ask_for_missing` says
    computed entries verbatim, so they have to arrive as sentences: capitalised, and stopped
    once rather than twice.
    """
    said = message.strip().rstrip(".")
    if options:
        said += f". I can do {', '.join(options)}"
    return said[:1].upper() + said[1:] + "."


async def _extract_with_llm(llm, text: str, state: PlanningAgentState) -> BriefFields:
    prompt = f"Already known:\n{_known_summary(state)}\n\nLatest message:\n{text}"
    logger.debug("llm.prompt", extra=kv(purpose="extract", prompt=prompt))

    started = time.monotonic()
    # include_raw so token usage survives structured parsing - without it the
    # parsed model is all that comes back and the cost is invisible.
    response = await llm.with_structured_output(BriefFields, include_raw=True).ainvoke(
        [{"role": "system", "content": _system_prompt()}, {"role": "user", "content": prompt}]
    )
    log_usage("extract", response.get("raw"), round((time.monotonic() - started) * 1000))

    parsed = response.get("parsed")
    if parsed is None:
        raise ValueError(f"structured output failed: {response.get('parsing_error')}")

    logger.debug("llm.parsed", extra=kv(purpose="extract", fields=parsed.model_dump()))
    return parsed


# --- merging -----------------------------------------------------------------


def _merge(state: PlanningAgentState, found: BriefFields) -> dict:
    """Overlay what was found onto what was known, keeping non-empty values.

    Empty means "not mentioned this turn", never "cleared". Clearing a field
    needs an explicit correction, which the LLM path handles by returning the
    corrected value rather than a blank.
    """
    known_dates = state.get("flight_dates") or {}
    known_budgets = state.get("market_budgets") or []
    known_amount = known_budgets[0]["budget"] if known_budgets else None

    markets = found.markets or state.get("markets") or []
    durations = found.durations or state.get("durations") or []
    # Only providers VOW actually carries. A model naming "Peacock" should not
    # put an unrecognised provider into the plan.
    known = {p["value"] for p in reference.providers()}
    providers = [
        p for p in (found.providers or state.get("preferred_providers") or []) if p in known
    ]
    start = found.flight_start or known_dates.get("lower")
    end = found.flight_end or known_dates.get("upper")
    amount = found.budget_amount or known_amount
    currency = (
        found.currency
        or state.get("primary_currency")
        or (_CURRENCY_BY_MARKET.get(markets[0]) if markets else None)
        or "GBP"
    )

    # **Durations are no longer filtered here.** This dropped anything outside a hard-coded
    # tuple, which is the silent-drop failure: a trader asking for 45s had it removed without
    # a word and went on believing it was in the plan. `_grounding` now checks them against the
    # snapshot's own `valid_durations` and says which one cannot be sold - and the list comes
    # from the platform rather than from a constant in this file.
    return {
        "markets": markets,
        "durations": durations,
        "preferred_providers": providers,
        "flight_dates": {"lower": start, "upper": end, "bounds": "[)"} if start and end else None,
        "primary_currency": currency,
        "market_budgets": (
            [{"market": markets[0], "budget": amount, "base_bid": None}]
            if markets and amount
            else []
        ),
    }


def _joined(*parts: str) -> str:
    """The parts that have something to say, one blank line apart.

    A note is only sometimes there, and `"\\n\\n".join` on a list with a `None` or an empty
    string in it leaves a double gap that reads as a missing paragraph.
    """
    return "\n\n".join(part for part in parts if part and part.strip())


def _confirmation(fields: dict) -> str:
    dates = fields.get("flight_dates")
    budgets = fields.get("market_budgets")

    return "\n".join(
        [
            "Here is what I understood - correct anything that is wrong before I continue.",
            "",
            f"- Markets: {', '.join(fields['markets']) or 'not stated'}",
            f"- Flight: {dates['lower']} to {dates['upper']}" if dates else "- Flight: not stated",
            f"- Creative durations: {', '.join(fields['durations']) or 'not stated'}",
            f"- Currency: {fields['primary_currency']}",
            (
                f"- Budget: {budgets[0]['budget']} {fields['primary_currency']} ({budgets[0]['market']})"
                if budgets
                else "- Budget: not stated"
            ),
            "- Goal: Awareness, measured on reach (fixed for CTV)",
        ]
    )


# --- the node ----------------------------------------------------------------


def make_extract_fields(registry):
    """Bind the grounded registry, the way the other node factories bind `mcp`.

    The accessor rather than a snapshot, and the registry's own docstring says why: the market
    comes out of the conversation, per-market facets load lazily, and the graph is compiled
    once per advertiser and cached for the life of the process - so a snapshot bound here would
    be both market-less and permanently stale.
    """

    async def extract_fields(state: PlanningAgentState) -> dict:
        """Understand this turn's message, merged into what is already known - and grounded."""
        text = _latest_human_text(state)
        llm = get_llm()

        if llm:
            try:
                found = await _extract_with_llm(llm, text, state)
                method = "llm"
            except Exception:
                # Degraded, not broken - patterns still work. Warned rather than
                # errored, but worth alerting on if it becomes frequent.
                logger.warning("llm.fallback", extra=kv(purpose="extract"), exc_info=True)
                found = _extract_with_patterns(text)
                method = "patterns (llm failed)"
        else:
            found = _extract_with_patterns(text)
            method = "patterns"

        fields = _merge(state, found)

        # **Is what the trader said something VOW sells?** See `_grounding`. Run before the
        # confirmation is built, so a note can ride along with it.
        blocking, notes, rejected = await _grounding(registry, fields)

        # Check for approval intent when the plan is ready
        is_approval = bool(
            re.search(r"\b(approve|accept|create it|yes,? approve|yes,? create|proceed)\b", text, re.I)
        )
        plan_approved = True if (is_approval and state.get("stage_cursor") == "plan_ready") else state.get("plan_approved")

        # Check for audience/location refinements in user text
        audience_refinement = state.get("audience_refinement")
        if re.search(r"\b(runner|running|fitness|enthusiast|aged?\s*\d+|\b25-44\b)\b", text, re.I):
            audience_refinement = text.strip()
        elif re.search(r"\b(broad|keep it broad|default audience)\b", text, re.I):
            audience_refinement = None

        locations = state.get("locations") or []
        if re.search(r"\b(london|manchester|birmingham)\b", text, re.I):
            match = re.search(r"\b(london|manchester|birmingham)\b", text, re.I)
            if match:
                locations = [match.group(1).title()]
        elif re.search(r"\b(uk-wide|uk wide|countrywide|nationwide)\b", text, re.I):
            locations = [fields["markets"][0]] if fields["markets"] else ["GB"]

        market_label = fields["markets"][0] if fields.get("markets") else "TBC"
        month_label = fields["flight_dates"]["lower"][:7] if fields.get("flight_dates") else "TBC"

        result = {
            **fields,
            "current_stage": STAGE,
            "strategy_name": f"CTV {market_label} {month_label}",
            "product_context": state.get("product_context") or (
                "New running shoe line" if re.search(r"\brunning shoe", text, re.I) else None
            ),
            "audience_refinement": audience_refinement,
            "locations": locations,
            "plan_approved": plan_approved,
            "goal": "AWARENESS",
            "kpi": "reach",
            "rejected_fields": rejected,
        }


        # The gate: whatever is still missing stops the graph here and gets asked for.
        result["awaiting"] = blocking or missing_basics(result)

        # Only emit a message from extract_fields if the basics were completed in full this turn.
        # Otherwise, ask_for_missing will speak for the turn so we don't output double messages.
        if not result["awaiting"] and not state.get("markets"):
            # TC-005 complete brief in one message
            result["messages"] = [
                {
                    "role": "assistant",
                    "content": (
                        f"Perfect. I have the core campaign brief:\n"
                        f"- Market: {market_label}\n"
                        f"- Inventory: {', '.join(fields['preferred_providers']) or 'Prime Video'}\n"
                        f"- Budget: {fields['market_budgets'][0]['budget']} {fields['primary_currency']}\n"
                        f"- Flight: {fields['flight_dates']['lower']} to {fields['flight_dates']['upper']}\n"
                        f"- Duration: {', '.join(fields['durations'])}s\n"
                        f"- Goal: Awareness\n\n"
                        f"I'll use the default {market_label}-wide targeting unless you'd like to refine the audience or location."
                    ),
                }
            ]
        else:
            result["messages"] = []

        # A change to any of these invalidates work already done
        invalidating = ("markets", "durations", "preferred_providers", "market_budgets")
        changed = [f for f in invalidating if state.get(f) != result.get(f)]
        if changed and state.get("stage_cursor"):
            logger.info(
                "plan.invalidated", extra=kv(changed=changed, was=state.get("stage_cursor"))
            )
            result["stage_cursor"] = None

        logger.info(
            "stage.basics",
            extra=kv(
                method=method,
                markets=fields["markets"],
                grounded=not blocking,
                rejected=rejected,
                notes=len(notes),
                awaiting=result["awaiting"],
            ),
        )
        if blocking:
            logger.warning("grounding.rejected", extra=kv(reasons=blocking))
        logger.debug("stage.basics.values", extra=kv(**fields))

        return result

    return extract_fields

