"""Node 1 - understand the brief, remembering what was already established.

Two behaviours that matter more than the parsing itself:

**It accumulates.** A trader supplies a brief over several messages, and answers
a follow-up with just "50,000". So this node merges into what is already known
rather than replacing it. Writing every field on every turn - including the
blank ones - would wipe the market as soon as someone answered a question about
budget, and the conversation could never converge.

Accumulating means holding *partial* answers too, which is why the raw
`flight_start` / `flight_end` / `budget_amount` slots exist alongside the
schema-shaped `flight_dates` and `market_budgets`. A budget cannot be keyed to a
market before one is named, and a flight needs both ends; the derived fields are
empty until whole, so they used to drop a half-answer on the floor and the agent
asked for it again next turn. `_known_summary` read the budget back out of
`market_budgets`, so the LLM prompt forgot it as well - both paths, one cause.

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
from datetime import date

from pydantic import BaseModel, Field

from app.agent.gates import missing_basics, say
from app.agent.llm import get_llm
from app.agent.state import PlanningAgentState
from app.core.logging import kv
from app.knowledge import reference
from app.knowledge.registry.models import CURRENCY_BY_MARKET, DurationEnum, duration_phrase

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

# Reference data, so it comes from the registry rather than being restated here.
# Both are static rather than snapshot lookups on purpose: this node runs before
# a market is known, so there is no per-market snapshot to consult yet. The
# regexes above stay - "britain" and "u.k." are linguistics, not reference data.
_CURRENCY_BY_MARKET = CURRENCY_BY_MARKET
_SYMBOL_CURRENCY = {"£": "GBP", "$": "USD", "€": "EUR"}

# The three audience shapes, as a trader names them. "broad" is here because v2
# renamed it Wide and a trader who read the old wording still means WIDE -
# `normalize_profile` maps the alias, so this only has to spot the word.
_PROFILE_PATTERNS = {
    "NARROW": r"\b(narrow|narrowest|tightest|most targeted)\b",
    "BALANCED": r"\b(balanced|balance|middle|recommended)\b",
    "WIDE": r"\b(wide|widest|broad|broadest)\b",
}

_VALID_DURATIONS = tuple(d.value for d in DurationEnum)
# "10, 15, 20 or 30", for the LLM's rules and the field description. From the
# registry, so this and the gate's question and the validator's rejection cannot
# disagree about what the platform sells.
_DURATION_PHRASE = duration_phrase()
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}

# Ordered by how strongly each signals "this number is money". Every pattern
# captures (symbol, number, magnitude_suffix) so the caller reads them alike.
# A bare number is never treated as a budget: in "August 2026 ... 30 second"
# most numbers in a brief are not money, and guessing wrong sets a real budget.
_BUDGET_PATTERNS = (
    r"([£$€])\s?([\d][\d,]*(?:\.\d+)?)\s*([km])?\b",  # £50,000 · $2.5m
    r"()([\d][\d,]*(?:\.\d+)?)\s*([km])\b",  # 50k
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
        description=f"Creative durations in seconds: only {_DURATION_PHRASE}",
    )
    budget_amount: str | None = Field(None, description="Decimal string, no symbol, e.g. 50000.00")
    currency: str | None = Field(None, description="GBP, USD or EUR")
    audience_profile: str | None = Field(
        None,
        description=(
            "Which of the three audience options the trader picked, if they named one: "
            "NARROW, BALANCED or WIDE. Leave empty unless they chose."
        ),
    )
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


def _audience_profile(text: str) -> str | None:
    """Which of the three options the trader named, if any.

    Word-boundary matched so "a wider audience" does not register as WIDE. Returns
    None when the message names none - answering "yes" to the options list is not
    a choice, and guessing one would commit budget against an audience nobody
    picked.
    """
    for code, pattern in _PROFILE_PATTERNS.items():
        if re.search(pattern, text, re.I):
            return code
    return None


def _budget(text: str) -> tuple[str | None, str | None]:
    """Return (amount, currency_from_symbol). Handles '£50,000', '50k', '1.2m', '15000 GBP'."""
    for pattern in _BUDGET_PATTERNS:
        match = re.search(pattern, text, re.I)
        if not match:
            continue

        symbol, raw, suffix = match.groups()
        amount = float(raw.replace(",", ""))
        if suffix:
            amount *= 1_000 if suffix.lower() == "k" else 1_000_000

        return f"{amount:.2f}", _SYMBOL_CURRENCY.get(symbol or "")

    # Check for number followed by currency code, e.g. "15000 GBP"
    curr_match = re.search(r"\b([\d][\d,]*(?:\.\d+)?)\s*(gbp|usd|eur)\b", text, re.I)
    if curr_match:
        raw, curr = curr_match.groups()
        amount = float(raw.replace(",", ""))
        return f"{amount:.2f}", curr.upper()

    return None, None


def _durations(text: str, valid: tuple[str, ...] = _VALID_DURATIONS) -> list[str]:
    """Creative durations named in the brief, in seconds.

    The alternation is built from `valid` rather than written out, so a length
    added to `DurationEnum` becomes extractable with no edit here. Written out,
    the enum would accept a new duration that this function could never find -
    the value would be silently dropped between the brief and the state.

    `valid` is injectable so a test can prove that property without adding a
    length to the enum, which is a cross-lane contract change.

    Caveat worth knowing before adding a short duration: the bare-number branch
    below matches any listed value once a unit word appears anywhere in the
    message, so "6 markets, 30 second creatives" would yield both. The risk
    scales with how ordinary the number is; the LLM path does not share it.
    """
    alternation = "|".join(sorted(valid, key=int))
    found = set(re.findall(rf"\b({alternation})\s*(?:s\b|sec|second)", text, re.I))

    # "15 and 30 second creatives" carries the unit only on the last number, so
    # once a unit word appears anywhere, bare durations in the same message
    # count too. Word boundaries keep budgets and years out: neither "50,000"
    # nor "2026" yields a bare match.
    if re.search(r"\b(?:secs?|seconds?)\b|\d\s*s\b", text, re.I):
        found.update(re.findall(rf"\b({alternation})\b", text))

    return sorted(found, key=int)


def _flight_dates(text: str) -> tuple[str | None, str | None]:
    match = re.search(rf"\b({'|'.join(_MONTHS)})\b(?:\s+(\d{{4}}))?", text, re.I)
    if not match:
        return None, None

    month = _MONTHS[match.group(1).lower()]
    today = date.today()
    if match.group(2):
        year = int(match.group(2))
    else:
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
        currency=symbol_currency,
        audience_profile=_audience_profile(text),
        providers=reference.provider_from_text(text),
    )


# --- the LLM path ------------------------------------------------------------


def _known_summary(state: PlanningAgentState) -> str:
    """What the model is told is already established."""
    return "\n".join(
        [
            f"markets: {state.get('markets') or 'unknown'}",
            f"flight_start: {state.get('flight_start') or 'unknown'}",
            f"flight_end: {state.get('flight_end') or 'unknown'}",
            f"durations: {state.get('durations') or 'unknown'}",
            f"budget_amount: {state.get('budget_amount') or 'unknown'}",
            f"currency: {state.get('primary_currency') or 'unknown'}",
            f"audience_profile: {state.get('audience_choice') or 'not chosen'}",
            f"providers: {state.get('preferred_providers') or 'unknown'}",
        ]
    )


def _system_prompt() -> str:
    """Dynamic system prompt carrying today's date."""
    today_str = date.today().isoformat()
    return (
        f"TODAY IS {today_str}.\n"
        "Extract connected-TV campaign details from a trader's message.\n"
        "You are given what is already known and the trader's latest message.\n"
        "Return the COMPLETE updated set: carry forward anything still true, apply "
        "any correction the message makes, and add anything new.\n"
        f"Rules: markets are ISO country codes. Durations may only be {_DURATION_PHRASE}. "
        "Dates are ISO YYYY-MM-DD. A month with no year means the NEXT TIME IT OCCURS, never the one just gone. "
        "If the trader states a specific year (including a past year, e.g. 2023), RETURN IT EXACTLY AS GIVEN — "
        "do not keep the previous value or sanitise it. "
        "Budget is a decimal string with no symbol. Leave a field empty if it is "
        "genuinely unknown - never guess a value the trader did not give."
    )


async def _extract_with_llm(llm, text: str, state: PlanningAgentState) -> BriefFields:
    prompt = f"Already known:\n{_known_summary(state)}\n\nLatest message:\n{text}"

    response = await llm.with_structured_output(BriefFields, include_raw=True).ainvoke(
        [{"role": "system", "content": _system_prompt()}, {"role": "user", "content": prompt}]
    )

    parsed = response.get("parsed")
    if not isinstance(parsed, BriefFields):
        raise ValueError(f"structured output failed: {response.get('parsing_error')}")

    return parsed


# --- merging -----------------------------------------------------------------


def _merge(state: PlanningAgentState, found: BriefFields) -> PlanningAgentState:
    """Overlay what was found onto what was known, keeping non-empty values.

    Empty means "not mentioned this turn", never "cleared". Clearing a field
    needs an explicit correction, which the LLM path handles by returning the
    corrected value rather than a blank.

    The raw slots are what is remembered; `flight_dates` and `market_budgets` are
    derived from them and only written when whole. Keeping both is the point: a
    half-answer survives in the raw slot so `gates.missing_basics` counts it as
    answered, while nothing downstream ever sees a partial dict.
    """
    markets = found.markets or state.get("markets") or []
    durations = found.durations or state.get("durations") or []
    # Only providers VOW actually carries. A model naming "Peacock" should not
    # put an unrecognised provider into the plan.
    known_providers = {p["value"] for p in reference.providers()}
    providers = [
        p
        for p in (found.providers or state.get("preferred_providers") or [])
        if p in known_providers
    ]
    start = found.flight_start or state.get("flight_start")
    end = found.flight_end or state.get("flight_end")
    amount = found.budget_amount or state.get("budget_amount")
    currency = (
        found.currency
        or state.get("primary_currency")
        or (_CURRENCY_BY_MARKET.get(markets[0]) if markets else None)
        or "GBP"
    )

    # Only keep durations the platform actually sells.
    durations = [d for d in durations if d in _VALID_DURATIONS]

    # An unrecognised profile is carried through rather than dropped, so
    # `suggest_audiences` can validate it and say what the three options are.
    # Silently discarding it would leave the trader repeating a word the agent
    # never acknowledged.
    choice = found.audience_profile or state.get("audience_choice")

    return {
        "markets": markets,
        "durations": durations,
        "preferred_providers": providers,
        "primary_currency": currency,
        "audience_choice": choice,
        # What the trader said, kept whether or not it can be shaped yet.
        "flight_start": start,
        "flight_end": end,
        "budget_amount": amount,
        # Derived, and only when whole - `predict_reach` sends `flight_dates` to
        # VOW, so a partially filled one must not exist.
        "flight_dates": {"lower": start, "upper": end, "bounds": "[)"} if start and end else None,
        "market_budgets": (
            [{"market": markets[0], "budget": amount, "base_bid": None}]
            if markets and amount
            else []
        ),
    }


def _confirmation(fields: PlanningAgentState) -> str:
    known = []
    if fields.get("markets"):
        known.append(f"Market: {', '.join(fields['markets'])}")
    if fields.get("flight_dates"):
        dates = fields["flight_dates"]
        known.append(f"Flight: {dates.get('lower')} to {dates.get('upper')}")
    elif fields.get("flight_start"):
        known.append(f"Flight start: {fields['flight_start']}")
    if fields.get("durations"):
        known.append(f"Creative: {', '.join(fields['durations'])}s")
    if fields.get("market_budgets"):
        b = fields["market_budgets"][0]
        known.append(f"Budget: {b.get('budget')} {fields.get('primary_currency', 'GBP')}")
    elif fields.get("budget_amount"):
        known.append(f"Budget: {fields['budget_amount']} {fields.get('primary_currency', 'GBP')}")
    if fields.get("preferred_providers"):
        known.append(f"Inventory: {', '.join(fields['preferred_providers'])}")

    if not known:
        return "Understood — let's plan your CTV campaign."
    return f"Understood: {', '.join(known)}."


def get_llm():
    """Retrieve LLM dynamically, allowing both module and package-level monkeypatching."""
    from app.agent import llm as llm_mod
    return llm_mod.get_llm()


async def extract_fields(state: PlanningAgentState) -> PlanningAgentState:
    """Understand this turn's message, merged into what is already known."""
    text = _latest_human_text(state)
    llm = get_llm()

    audited = dict(state.get("audited") or {})

    # Recorded rather than inferred, because the three paths are indistinguishable
    # from the resulting state and they are not the same audit fact: "the model
    # proposed CN and the registry rejected it" is a different claim from "a regex
    # read CN". `validate_basics` reads this when it states its verdict.
    if llm:
        # What the prompt is actually constrained by, stated narrowly on purpose.
        # The only registry-derived rule in `_SYSTEM` is the duration vocabulary,
        # from `registry.models.DurationEnum` via `duration_phrase()` - a static
        # list of what the platform sells, not a per-advertiser snapshot.
        #
        # `snapshot_consulted=False` is recorded explicitly so this cannot be read
        # as a stronger claim than it is: this node runs before a market is known,
        # so there is no snapshot to constrain against. Grounding happens after
        # extraction, in `validate_basics`.
        #
        # Once per session. The payload is a constant - it was byte-identical on
        # all nine turns of the sample log - so repeating it says nothing new. It
        # sits inside this branch rather than at the top of the node because it
        # describes a prompt, and without an LLM no prompt is built.
        if not audited.get("constraints"):
            logger.info(
                "audit.prompt_constraints",
                extra=kv(
                    allowed_durations=list(_VALID_DURATIONS),
                    constraint_source="registry.models.DurationEnum",
                    snapshot_consulted=False,
                ),
            )
            audited["constraints"] = True

        try:
            found = await _extract_with_llm(llm, text, state)
            method = "llm"
        except Exception:
            # Degraded, not broken - patterns still work. Warned rather than
            # errored for that reason, but worth alerting on if it becomes
            # frequent: a silent fallback is how a model that has stopped
            # answering goes unnoticed for a week.
            logger.warning("llm.fallback", extra=kv(purpose="extract"), exc_info=True)
            found = _extract_with_patterns(text)
            method = "patterns_after_llm_failure"
    else:
        found = _extract_with_patterns(text)
        method = "patterns"

    fields = _merge(state, found)

    # Provisional name only - uniqueness must be checked against VOW before use.
    market_label = fields["markets"][0] if fields["markets"] else "TBC"
    # Off the raw slot, so a start date given without an end still names a month.
    month_label = fields["flight_start"][:7] if fields["flight_start"] else "TBC"

    # Silent when the confirmation would be word-for-word what it was last turn.
    # `say` compares the prose rather than the fields, which is the same test one
    # step later and generalises to every other stage - see `gates.say`.
    spoken = say(state, STAGE, _confirmation(fields))

    result: PlanningAgentState = {
        **fields,
        **spoken,
        "current_stage": STAGE,
        "extraction_method": method,
        # Spread, not replaced: `validate_basics` writes its own keys into this
        # same dict later in the turn, and LangGraph overwrites a dict value
        # wholesale. Same constraint `say` has on `last_said`.
        "audited": audited,
        "strategy_name": f"CTV {market_label} {month_label}",
        "goal": "AWARENESS",
        "kpi": "reach",
    }

    # The gate: whatever is still unanswered stops the graph here and gets asked
    # for, one item at a time. Computed against the merged result, so a value
    # supplied this turn counts as answered immediately.
    result["awaiting"] = missing_basics(result)

    # Nothing is validated here. Grounding a value needs the registry and a
    # market, and this node runs before either is settled - `validate_basics` owns
    # it, which is also why a flight starting in the past now stops the flow
    # rather than being noted and planned around.

    # A change to any of these invalidates work already done: deals are filtered
    # by market, duration and provider; audiences are priced from the deals; the
    # forecast comes from the audience. "Use Netflix instead" makes every value
    # below it stale.
    #
    # Recorded rather than acted on, because the gated chain already re-runs every
    # stage from here on the next turn - so the re-plan is the default and needs no
    # trigger. What is not free is *knowing* it happened: `plan.invalidated` is how
    # a support question about a number that changed mid-conversation gets an
    # answer. `stage_cursor` is rewound to keep the recorded progress honest about
    # the fact that downstream work no longer describes the current plan.
    invalidating = ("markets", "durations", "preferred_providers", "market_budgets")
    changed = [field for field in invalidating if state.get(field) != result.get(field)]
    if changed and state.get("stage_cursor"):
        logger.info("plan.invalidated", extra=kv(changed=changed, was=state.get("stage_cursor")))
        result["stage_cursor"] = None

    logger.info(
        "stage.basics",
        extra=kv(
            method=method,
            markets=fields["markets"],
            fields_found=f"{4 - len(result['awaiting'])}/4",
            awaiting=result["awaiting"],
        ),
    )
    # Budgets and dates are client-commercial; the shape is enough at INFO.
    logger.debug("stage.basics.values", extra=kv(**fields))

    return result
