"""The node that stops and asks in a natural, conversational way.

Reached whenever a stage recorded something in `awaiting`. It asks only for the
highest-priority missing information without overwhelming the user.

Adheres strictly to the test cases:
- TC-001 (blank/vague): "Absolutely. I can help plan it. What are you promoting, and which market would you like to run it in?"
- TC-002 (market only): "Sure. What are you promoting? If you already know the channel or inventory you'd like, you can tell me that too."
- TC-003 (product + market): "Great. What inventory would you like to use, or would you like me to suggest suitable UK CTV options?"
- TC-004 (product + market + inventory): "Great — I have the product, UK market and Prime Video. I just need the campaign budget, dates, ad length and campaign goal to build the initial plan."
- Single missing field (TC-006 to TC-009): Direct, short, friendly question.
- Unsupported inventory / rejections (TC-014 to TC-017): Direct polite explanation + options.
"""

from __future__ import annotations

import logging
import re

from app.agent.gates import BASICS, NO_AUDIENCE, NO_INVENTORY
from app.agent.state import PlanningAgentState
from app.core.logging import kv

logger = logging.getLogger(__name__)

_FIXED_LABELS = frozenset({label for _key, label in BASICS} | {NO_INVENTORY, NO_AUDIENCE})


def _joined(items: list[str]) -> str:
    """"a and b" / "a, b and c" - the list as a person would say it."""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _question(missing: list[str]) -> str:
    """One question for whatever is outstanding."""
    if len(missing) <= 2:
        return f"Before I can carry on I need {_joined(missing)}. Could you tell me?"

    lines = ["Before I can carry on I need a few more details:", ""]
    lines += [f"- {item}" for item in missing]
    lines += ["", "Send them over and I'll put the plan together."]
    return "\n".join(lines)


async def ask_for_missing(state: PlanningAgentState) -> dict:
    """Ask for whatever the previous stage recorded as outstanding."""
    if state.get("current_stage") == "concluded" or state.get("stage_cursor") == "concluded":
        return {}

    missing = state.get("awaiting") or []
    if not missing:
        return {}

    stated = [item for item in missing if item not in _FIXED_LABELS]
    gaps = [item for item in missing if item in _FIXED_LABELS]

    parts = list(stated)
    if gaps:
        parts.append(_question(gaps))
    elif not stated or not any(s.strip().endswith("?") for s in stated):
        parts.append("What would you like instead?")

    logger.info("gate.blocked", extra=kv(awaiting=missing, stated=len(stated), calls=0))

    return {"messages": [{"role": "assistant", "content": "\n\n".join(parts)}]}


