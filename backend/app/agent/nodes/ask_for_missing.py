"""The node that stops and asks in a natural, conversational way.

Reached whenever a stage recorded something in `awaiting`. It uses Claude to
generate a short, natural response that:
  - Acknowledges what was already understood (never asks for it again)
  - Asks only for the single most important missing thing
  - Feels like a human campaign-planning assistant, not a form

If Claude is unavailable, falls back to a concise template.

M1 Planning Rules (from M1_planning.txt):
- Step 8: Ask for NEXT meaningful decision only, not a questionnaire
- Step 16: Responses must feel real-time and human
- Step 5: Deeply analyse what the user said - confirm what was understood
- Never re-ask information already provided
"""

from __future__ import annotations

import logging
import time

from app.agent.gates import BASICS, NO_AUDIENCE, NO_INVENTORY
from app.agent.llm import get_llm, log_usage
from app.agent.state import PlanningAgentState
from app.core.logging import kv

logger = logging.getLogger(__name__)

_FIXED_LABELS = frozenset({label for _key, label in BASICS} | {NO_INVENTORY, NO_AUDIENCE})


def _joined(items: list[str]) -> str:
    """"a and b" / "a, b and c" - the list as a person would say it."""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _known_summary(state: PlanningAgentState) -> str:
    """Build a short human-readable summary of what we already know."""
    parts = []
    if state.get("brand"):
        parts.append(f"Brand: {state['brand']}")
    elif state.get("product_context"):
        parts.append(f"Product/campaign: {state['product_context']}")
    markets = state.get("markets") or []
    if markets:
        market_labels = {"GB": "UK", "US": "USA", "FR": "France", "DE": "Germany"}
        parts.append(f"Market: {', '.join(market_labels.get(m, m) for m in markets)}")
    if state.get("flight_dates"):
        fd = state["flight_dates"]
        parts.append(f"Flight: {fd.get('lower', '?')} to {fd.get('upper', '?')}")
    durations = state.get("durations") or []
    if durations:
        parts.append(f"Creative: {', '.join(durations)}s")
    budgets = state.get("market_budgets") or []
    if budgets:
        b = budgets[0]
        currency = state.get("primary_currency", "GBP")
        parts.append(f"Budget: {b.get('budget', '?')} {currency}")
    preferred = state.get("preferred_providers") or []
    if preferred:
        parts.append(f"Inventory: {', '.join(preferred)}")
    return "\n".join(f"- {p}" for p in parts) if parts else "Nothing known yet."


def _fallback_question(missing: list[str], state: PlanningAgentState) -> str:
    """Simple template used when Claude is unavailable."""
    stated_parts = [item for item in missing if item not in _FIXED_LABELS]
    gap_parts = [item for item in missing if item in _FIXED_LABELS]

    # If it's a rejection/conflict message (TC-014 etc), surface it directly
    if stated_parts:
        return stated_parts[0]

    # For missing basics, ask for the most critical one
    if gap_parts:
        if len(gap_parts) == 1:
            return f"I just need {gap_parts[0]}. Could you let me know?"
        if len(gap_parts) == 2:
            return f"I still need {_joined(gap_parts)}. Could you send those over?"
        lines = ["I need a few more details to continue:", ""]
        lines += [f"- {g}" for g in gap_parts]
        lines += ["", "Send them over and I'll put the plan together."]
        return "\n".join(lines)

    return "What would you like instead?"


def _build_system_prompt() -> str:
    return """You are a smart, friendly CTV campaign-planning assistant for the VOW platform.
Your job is to help traders build a campaign strategy through natural conversation.

STYLE RULES:
- Be concise and conversational — 1-3 sentences maximum
- Sound like a helpful human, not a system or form
- Acknowledge what you understood before asking what's missing or explaining an issue
- Ask for ONE thing at a time (the most important missing piece)
- Never list all missing fields as bullet points
- Never say "Before I can carry on I need:" — this sounds robotic
- Use contractions: "I've got" not "I have got", "don't" not "do not"
- Keep it warm, direct, and professional

VALIDATION & ANTI-HALLUCINATION RULES:
- If flight dates are in the past: State clearly: "Those dates have already passed. Campaign flight dates must be upcoming. Please select a future start and end date." NEVER suggest reviewing past campaigns or historical reports.
- If creative duration is unsupported (e.g. 45s, 60s): State clearly: "We don't offer [X]-second spots on CTV. We support 10s, 15s, 20s, or 30s instead. Which duration works best for you?"
- If requested inventory is not carried (e.g. Zee TV, Sony Liv): State clearly that it is not available on the platform and offer to show available inventory.
- Never invent platform features or campaign data.

EXAMPLES OF GOOD RESPONSES:
- "Got it — running shoes in the UK. When are you planning to run the campaign?"
- "Those dates have already passed. Campaign flight dates must be upcoming. When would you like the campaign to run?"
- "We don't offer 45-second spots on CTV. We support 10s, 15s, 20s, or 30s instead. Which duration works best for you?"
- "Great. I've got most of the details. What creative duration works best — 15s or 30s?"
- "I've got the brief. What's your budget for the campaign?"

EXAMPLES OF BAD RESPONSES (never do these):
- "or were you looking to review a past campaign?" (NEVER say this)
- "Before I can carry on I need: - the start and end dates - the budget - the creative duration"
- "Please provide the following information: market, dates, budget"
"""


async def _llm_ask(llm, state: PlanningAgentState, missing: list[str]) -> str:
    """Use Claude to generate a natural, context-aware response."""
    known = _known_summary(state)
    stated = [m for m in missing if m not in _FIXED_LABELS]
    gaps = [m for m in missing if m in _FIXED_LABELS]

    # Build a clear context for Claude
    context_parts = [f"What I already know about this campaign:\n{known}"]

    if stated:
        # These are blocking messages (channel conflicts, validation errors)
        context_parts.append(f"Blocking issue to communicate:\n{stated[0]}")
        context_parts.append("Generate a short, friendly message explaining this issue and asking what the trader wants to do.")
    elif gaps:
        priority_gap = gaps[0]  # First = most important (ordering from gates.BASICS)
        context_parts.append(f"What's still missing (ask for the most important one):\n- {priority_gap}")
        if len(gaps) > 1:
            context_parts.append(f"Other things also missing (do NOT ask for these yet, just focus on the first one):\n{chr(10).join(f'- {g}' for g in gaps[1:])}")
        context_parts.append(
            "Generate ONE short, friendly question that:\n"
            "1. Briefly acknowledges what you already know (if anything)\n"
            "2. Asks ONLY for the single most important missing piece\n"
            "3. Sounds like a real human assistant"
        )
    else:
        context_parts.append("Ask what the trader would like to do next.")

    prompt = "\n\n".join(context_parts)

    started = time.monotonic()
    response = await llm.ainvoke([
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": prompt},
    ])
    log_usage("ask", response, round((time.monotonic() - started) * 1000))

    return response.content.strip() if hasattr(response, "content") else str(response).strip()


async def ask_for_missing(state: PlanningAgentState) -> dict:
    """Ask for whatever the previous stage recorded as outstanding.
    
    Uses Claude to generate natural, context-aware conversational responses.
    Falls back to a concise template if Claude is unavailable.
    """
    if state.get("current_stage") == "concluded" or state.get("stage_cursor") == "concluded":
        return {}

    missing = state.get("awaiting") or []
    if not missing:
        return {}

    llm = get_llm()
    reply_text = None

    if llm:
        try:
            reply_text = await _llm_ask(llm, state, missing)
        except Exception:
            logger.warning("llm.fallback", extra=kv(purpose="ask"), exc_info=True)

    if not reply_text:
        reply_text = _fallback_question(missing, state)

    logger.info(
        "gate.blocked",
        extra=kv(
            awaiting=missing,
            stated=len([m for m in missing if m not in _FIXED_LABELS]),
            llm_used=bool(llm and reply_text),
        ),
    )

    return {"messages": [{"role": "assistant", "content": reply_text}]}
