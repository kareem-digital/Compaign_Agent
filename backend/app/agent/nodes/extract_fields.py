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
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})

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
        default_factory=list,
        description="Creative durations in seconds mentioned by the trader, e.g. ['10'], ['15'], ['30'], ['45']. Return whatever number they gave — deciding whether it is supported is not your job.",
    )
    budget_amount: str | None = Field(None, description="Decimal string, no symbol, e.g. 50000.00")
    currency: str | None = Field(None, description="GBP, USD or EUR")
    providers: list[str] = Field(
        default_factory=list,
        description="CTV providers named, exactly as: Prime Video, Netflix, Disney+, Hulu",
    )
    product_context: str | None = Field(
        None,
        description="Brand, product or campaign description the trader mentions, e.g. 'running shoes', 'coffee brand launch', 'Nike Air Max'. Leave null if not stated.",
    )
    goal: str | None = Field(
        None,
        description="Campaign goal if explicitly stated: AWARENESS, CONSIDERATION, or CONVERSION. Leave null if not mentioned — the default will be applied.",
    )
    kpi: str | None = Field(
        None,
        description="KPI if explicitly stated: REACH, FREQUENCY, CTR, CPDPV, CPA, ROAS. Leave null if not mentioned.",
    )


# --- reading the conversation ------------------------------------------------


def _latest_human_text(state: PlanningAgentState) -> str:
    """The most recent user message, however LangGraph happens to store it."""
    messages = state.get("messages") or []
    for message in reversed(messages):
        role = getattr(message, "type", None) or (
            message.get("role") if isinstance(message, dict) else None
        )
        if role in ("human", "user"):
            if isinstance(message, dict):
                content = message.get("content", "")
            else:
                content = getattr(message, "content", "")

            if isinstance(content, list):
                content = " ".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
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
    found = set(re.findall(r"\b(\d+)\s*(?:s\b|sec|second)", text, re.I))

    # Once a unit word appears anywhere, bare durations in the same message count too.
    if re.search(r"\b(?:secs?|seconds?)\b|\d\s*s\b", text, re.I) or re.match(r"^\s*(\d+)\s*$", text.strip()):
        found.update(re.findall(r"\b(\d+)\b", text))

    return sorted(found, key=int)


def _flight_dates(text: str) -> tuple[str | None, str | None]:
    # Match ISO date range: e.g. '2026-10-01 to 2026-10-31' or '2026-10-01 - 2026-10-31'
    m_iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\s*(?:to|-)\s*(\d{4}-\d{2}-\d{2})\b", text)
    if m_iso:
        return m_iso.group(1), m_iso.group(2)

    # Match explicit day range: e.g. '1 Oct to 31 Oct 2026' or '1 October to 31 October 2026'
    m_range = re.search(
        rf"\b([1-9]|[12]\d|3[01])\s+({'|'.join(_MONTHS)})\b(?:\s+(?:to|-|until|through)\s+)?\b([1-9]|[12]\d|3[01])?\s*({'|'.join(_MONTHS)})\b(?:\s+(\d{{4}}))?",
        text,
        re.I,
    )
    if m_range:
        d1, m1_str, d2, m2_str, y_str = m_range.groups()
        m1 = _MONTHS[m1_str.lower()]
        m2 = _MONTHS[m2_str.lower()]
        if y_str:
            year = int(y_str)
        else:
            today = date.today()
            year = today.year if m1 >= today.month else today.year + 1
        return f"{year:04d}-{m1:02d}-{int(d1):02d}", f"{year:04d}-{m2:02d}-{int(d2 or d1):02d}"

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


_NON_PROVIDER_WORDS = {
    "uk", "gb", "us", "usa", "france", "germany", "china", "india", "japan", "spain",
    "italy", "australia", "canada", "brazil", "mexico", "awareness", "consideration",
    "campaign", "budget", "october", "september", "august", "january", "february",
    "march", "april", "may", "june", "july", "november", "december", "dollars",
    "pounds", "gbp", "usd", "eur", "running", "shoes", "shoe", "coffee", "brand",
    "line", "launch", "product", "details", "plan", "option", "options", "ads",
    "creative", "durations", "length", "lengths", "days", "dates", "flight",
    "target", "reach", "audience", "location", "postcode", "radius", "city",
    "show_alternatives", "keep_requested", "alternatives", "available",
    "keep", "no", "yes", "instead", "don't", "stop", "please", "thanks", "thank",
}


def _providers(text: str) -> list[str]:
    found_known = reference.provider_from_text(text)
    if found_known:
        return found_known

    # Catch channel/inventory requests such as "on Zee TV", "on the Zee TV", "using Peacock", "via Hotstar"
    matches = re.findall(
        r"\b(?:on|via|using)\s+(?:the\s+)?([a-z0-9\+\s]{2,25}?)(?:\s+(?:in|for|with|from|to|at|and|or|\d|\$|£|€)|$|\.|\?)",
        text,
        re.I,
    )
    unrecognized = []
    for match in matches:
        cand = match.strip()
        cand_lower = cand.lower()
        if (
            cand_lower
            and cand_lower not in _NON_PROVIDER_WORDS
            and len(cand_lower) >= 2
            and not re.match(r"^\d+$", cand_lower)
        ):
            title_cand = " ".join(
                w.upper() if w.lower() in ("tv", "dsp", "ott", "ctv") else w.capitalize()
                for w in cand.split()
            )
            unrecognized.append(title_cand)

    return unrecognized


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
        providers=_providers(text),
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
            f"brand: {state.get('brand') or 'unknown'}",
            f"product_context: {state.get('product_context') or 'unknown'}",
            f"goal: {state.get('goal') or 'unknown'}",
            f"kpi: {state.get('kpi') or 'unknown'}",
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
        "Rules: markets are ISO country codes. Extract any creative durations in seconds mentioned "
        "(e.g. 10, 15, 20, 30, 45, 60). Return whatever duration they asked for — deciding whether "
        "it is supported is not your job. Dates are ISO YYYY-MM-DD; a bare month means its first and last day.\n"
        "A DATE WITH NO YEAR MEANS THE NEXT TIME IT OCCURS, resolved forward from "
        "today: a trader saying 'October' means the next October to come, never the "
        "one just gone.\n"
        "WHEN THE TRADER STATES A YEAR, RETURN IT EXACTLY AS GIVEN - including a past "
        "one. Do not correct it and do not keep the previous value instead. Reporting "
        "what they said is your job; deciding whether it can be used is not.\n"
        "PROVIDERS: extract any channel, network, or inventory provider names the trader "
        "mentions (e.g. 'Prime Video', 'Netflix', 'Zee TV', 'Peacock'). Return the exact "
        "names they asked for — deciding whether the platform carries them is not your job.\n"
        "GOAL: extract the campaign goal ONLY if explicitly stated. Valid values: "
        "AWARENESS, CONSIDERATION, CONVERSION. If the trader says 'awareness' extract AWARENESS. "
        "If not stated, return null — do NOT default it here.\n"
        "KPI: extract the KPI ONLY if explicitly stated. Valid values: REACH, FREQUENCY, "
        "CTR, CPDPV, CPA, ROAS. If not stated, return null.\n"
        "BRAND: extract the advertiser brand name if mentioned "
        "(e.g. 'Nike', 'Mega Toothpaste', 'Adidas'). Carry forward the "
        "existing value if not changed. Leave null if genuinely not mentioned.\n"
        "PRODUCT_CONTEXT: extract any further context about the product launch or "
        "campaign description if mentioned (e.g. 'running shoes', 'launch', "
        "'new seasonal campaign'). Carry forward the existing value if not changed.\n"
        "Budget is a decimal string with no symbol. Leave a field empty if it is "
        "genuinely unknown - never guess a value the trader did not give."
    )


# The validator names a field as the schema does; `PlanningAgentState` sometimes names it
# differently. One mapping, in the one place the two vocabularies meet.
_PLAN_FIELD = {"target_markets": "markets"}


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


def _merge(state: PlanningAgentState, found: BriefFields) -> tuple[dict, list[str]]:
    """Overlay what was found onto what was known, keeping non-empty values.

    Empty means "not mentioned this turn", never "cleared". Clearing a field
    needs an explicit correction, which the LLM path handles by returning the
    corrected value rather than a blank.

    Returns (fields_dict, unavailable_providers) — the second element being any
    provider names the trader gave that the platform does not carry. Callers
    must surface these before asking for missing basics (TC-014).
    """
    known_dates = state.get("flight_dates") or {}
    known_budgets = state.get("market_budgets") or []
    known_amount = known_budgets[0]["budget"] if known_budgets else None

    markets = found.markets or state.get("markets") or []
    durations = found.durations or state.get("durations") or []
    # Only providers VOW actually carries. A model naming "Peacock" should not
    # put an unrecognised provider into the plan.
    known = {p["value"] for p in reference.providers()}
    newly_requested_providers = found.providers or []
    effective_providers = found.providers or state.get("preferred_providers") or []
    providers = [p for p in effective_providers if p in known]
    # Track what was dropped so the node can surface it (TC-014).
    unavailable_providers = [p for p in newly_requested_providers if p not in known]
    # Also carry forward any previously unavailable ones that are still unresolved.
    prev_unavailable = state.get("unavailable_requested_channels") or []
    unavailable_providers = unavailable_providers or prev_unavailable

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
    fields = {
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
    return fields, unavailable_providers


def _joined(*parts: str) -> str:
    """The parts that have something to say, one blank line apart.

    A note is only sometimes there, and `"\\n\\n".join` on a list with a `None` or an empty
    string in it leaves a double gap that reads as a missing paragraph.
    """
    return "\n\n".join(part for part in parts if part and part.strip())


def providers_resolved(state: PlanningAgentState, unavailable: list[str]) -> bool:
    """True when the trader has already been told about these unavailable providers.

    Once the channel-conflict message has been shown (awaiting_choice is set),
    we don't re-block on it every turn — the user's next reply is their answer.
    """
    # If awaiting_choice is set, the user was already shown the conflict and
    # their next message is a response to it.
    return bool(state.get("awaiting_choice"))


def _confirmation(fields: dict) -> str:
    dates = fields.get("flight_dates")
    budgets = fields.get("market_budgets")
    goal_val = fields.get("goal", "AWARENESS")
    kpi_val = fields.get("kpi", "REACH")

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
            f"- Goal: {goal_val.title()}, KPI: {kpi_val.title()}",
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

        # Safety net: if pattern matching found providers that LLM omitted, merge them
        pattern_provs = _providers(text)
        if pattern_provs and not found.providers:
            found.providers = pattern_provs

        fields, unavailable_providers = _merge(state, found)

        # **Is what the trader said something VOW sells?** See `_grounding`. Run before the
        # confirmation is built, so a note can ride along with it.
        blocking, notes, rejected = await _grounding(registry, fields)

        # Do not accept rejected values into the plan state
        if "flight_dates" in rejected:
            fields["flight_dates"] = None
        if "durations" in rejected:
            fields["durations"] = [d for d in (fields.get("durations") or []) if d in ("10", "15", "20", "30")]
        if "markets" in rejected:
            fields["markets"] = []
        if "primary_currency" in rejected:
            fields["primary_currency"] = "GBP"

        force_show_inventory = False
        awaiting_choice = state.get("awaiting_choice")
        # Handle user answer to previous channel conflict prompt (TC-015 / TC-016)
        if awaiting_choice == "unavailable_channel":
            if re.search(r"\b(yes|show|alternatives|available|options|show_alternatives|inventory|show available inventory)\b", text, re.I):
                # User wants to see available inventory. Clear the conflict state and
                # route directly to select_inventory to display the real deals!
                unavailable_providers = []
                awaiting_choice = None
                state["unavailable_requested_channels"] = []
                found.providers = []
                fields["preferred_providers"] = []
                blocking = []
                force_show_inventory = True
            elif re.search(r"\b(no|keep|don't|stop|later|plan later|keep_requested)\b", text, re.I):
                chan_name = ", ".join(state.get("unavailable_requested_channels") or ["that channel"])
                return {
                    "messages": [{
                        "role": "assistant",
                        "content": f"No problem. We hope to support {chan_name} in the future. You can come back anytime when you're ready to continue with a different inventory."
                    }],
                    "current_stage": "concluded",
                    "stage_cursor": "concluded",
                    "plan_approved": False,
                    "awaiting": [],
                    "awaiting_choice": None,
                    "unavailable_requested_channels": [],
                }
        elif awaiting_choice == "select_alternative_provider":
            # Legacy state: if the user somehow arrives here, treat it as cleared.
            awaiting_choice = None
        elif re.search(r"\b(show available inventory|show inventory|what inventory)\b", text, re.I):
            force_show_inventory = True

        # TC-014: If the trader named a provider the platform doesn't carry, surface it
        # IMMEDIATELY — before asking for missing basics (Rule C).
        if unavailable_providers and not providers_resolved(state, unavailable_providers):
            channel_names = ", ".join(unavailable_providers)
            channel_msg = (
                f"{channel_names} isn't currently available as inventory on this platform, "
                f"so I can't plan the campaign on it. We hope to support it in the future. "
                f"Would you like to use an available inventory instead?"
            )
            blocking = [channel_msg]
            awaiting_choice = "unavailable_channel"

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

        # brand: use the LLM-extracted value from BriefFields if it arrived,
        # falling back to whatever is already in state. Accumulates correctly across turns.
        # Distinct from strategy_name (system-generated) and product_context (backward compat).
        brand = found.product_context or state.get("brand")
        # product_context kept for plan_ready.py backward compat — mirrors brand.
        product_context = brand or state.get("product_context")

        # Goal: schema-driven default (AWARENESS per Schema v4.0 §4.8).
        # Not a constant — user can change it. Agent advises on non-Awareness, never blocks.
        extracted_goal = (found.goal or "").upper().strip()
        valid_goals = {g["value"] for g in reference.goals()}
        if extracted_goal and extracted_goal in valid_goals:
            goal = extracted_goal
        else:
            # Carry forward what was previously set; default to AWARENESS
            goal = state.get("goal") or "AWARENESS"

        # KPI: derived from goal per schema v4.0 §4.8.
        extracted_kpi = (found.kpi or "").upper().strip()
        valid_kpis_for_goal = {k["value"] for k in reference.kpis_for_goal(goal)}
        if extracted_kpi and extracted_kpi in valid_kpis_for_goal:
            kpi = extracted_kpi
        else:
            # Carry forward or default to the goal's default KPI
            prev_kpi = (state.get("kpi") or "").upper()
            if prev_kpi in valid_kpis_for_goal:
                kpi = prev_kpi
            else:
                default_kpi_entry = reference.default_kpi(goal)
                kpi = default_kpi_entry["value"] if default_kpi_entry else "REACH"

        # Advisory note: if the user explicitly picked a non-Awareness goal,
        # surface the advisory (schema says: advise, do not block).
        goal_advisory = None
        if goal != "AWARENESS" and goal != state.get("goal"):
            goal_record = next((g for g in reference.goals() if g["value"] == goal), None)
            if goal_record and goal_record.get("advisory_note"):
                goal_advisory = goal_record["advisory_note"]

        result = {
            **fields,
            "current_stage": STAGE,
            "strategy_name": f"CTV {market_label} {month_label}",
            "brand": brand,
            "product_context": product_context,
            "audience_refinement": audience_refinement,
            "locations": locations,
            "plan_approved": plan_approved,
            "goal": goal,
            "kpi": kpi,
            "rejected_fields": rejected,
            # Persist unavailable channels so they survive across turns (TC-014)
            "unavailable_requested_channels": [] if awaiting_choice is None and not unavailable_providers else (unavailable_providers or state.get("unavailable_requested_channels") or []),
            "awaiting_choice": awaiting_choice,
        }

        # If there's a goal advisory note, prepend it to blocking so the agent surfaces it
        if goal_advisory:
            blocking = [goal_advisory] + blocking

        # The gate: whatever is still missing stops the graph here and gets asked for.
        if force_show_inventory:
            result["awaiting"] = []
            result["stage_cursor"] = None
        else:
            result["awaiting"] = blocking or missing_basics(result)
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

