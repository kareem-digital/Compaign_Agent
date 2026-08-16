"""The node that stops and asks - one thing at a time.

Reached whenever a stage recorded something in `awaiting` or a validation
blocker. It asks about exactly one of them and ends the turn; the graph does not
continue until the trader replies.

**One question per turn.** This used to ask for everything outstanding at once,
on the reasoning that drip-feeding would be four round trips to start a plan -
the wizard experience the agent exists to replace. That was reversed
deliberately: a batched question reads as a form, and the round-trip cost is only
paid by a trader who volunteers nothing, because a full brief still answers every
item in one message and asks nothing. `gates.next_question` picks the item; this
node only phrases it.

**Never something already answered.** Both `awaiting` and the blocker list are
derived from current state every turn, so an answer given out of order removes an
item rather than being asked for again. That property lives in
`gates.missing_basics` and `gates.record`, not here.

**Conflicts before gaps**, because an invalid value keeps blocking whatever else
is collected. See `gates.next_question`.

No recap of what is already known: `extract_fields._confirmation` prints that
whenever the turn moved something, and saying it twice in one reply reads as the
agent having lost its place.

Either way the *content* is computed, never generated - a model rewords a known
question, it does not decide what is missing or what the alternatives are.

**Who does the wording depends on the voice layer.** When `agent.voice` is active
it re-voices the whole turn at the API boundary, so this node emits its template
and lets that single pass phrase it: the question is one block among several, and
a question phrased here would then be paraphrased again, which is both a wasted
call and a game of telephone. With the voice layer off - no key, or disabled -
this node phrases its own question as it always did, because then nothing else
will.
"""

from __future__ import annotations

import logging

from app.agent.gates import next_question
from app.agent.llm import get_llm
from app.agent.prompts import ASK_CONFLICT, ASK_MISSING
from app.agent.state import PlanningAgentState
from app.config import get_settings
from app.core.logging import kv

logger = logging.getLogger(__name__)


def _missing_template(label: str) -> str:
    """Deterministic phrasing for a gap, used when no LLM is configured."""
    return f"Before I can carry on I need {label}. Could you tell me?"


def _conflict_template(entry: dict) -> str:
    """Deterministic phrasing for an unsupported value.

    Renders `message` and `suggested_options` and nothing else - no branch on
    which field failed, which is what lets a validation rule added tomorrow reach
    the trader without a change in this file.

    `message` already names the offending value: the registry's validators are
    written for exactly this moment ("I cannot plan for XX - VOW does not sell
    CTV inventory there"), so a separate "you asked for" line would only repeat
    it. `field`, `code` and `metadata` ride along in state for the UI.
    """
    lines = [entry.get("message") or "One of the values you gave is not supported."]
    options = _options(entry)

    if options:
        lines.append(f"Available options: {options}")
        lines.append("Which would you like to use?")
    else:
        # Nothing to offer, so do not imply there is - a validation failure with no
        # alternatives ("that date has passed") needs a different closing question.
        lines.append("What would you like to change it to?")

    return "\n".join(lines)


def _options(entry: dict) -> str:
    return ", ".join(str(option) for option in entry.get("suggested_options") or [])


def _prompt(question: dict) -> tuple[str, str, str]:
    """(system prompt, user prompt, deterministic fallback) for one question."""
    if question["kind"] == "conflict":
        entry = question["entry"]
        options = _options(entry)
        # Bare sentences, no field labels. The model copies whatever scaffolding it
        # is handed - a "Problem:" prefix came back at the trader verbatim - and
        # the options line is omitted entirely rather than sent as "none".
        user = entry.get("message") or "A value the trader gave is not supported."
        if options:
            user += f"\n\nThe options available are: {options}"
        return ASK_CONFLICT, user, _conflict_template(entry)

    label = question["label"]
    return ASK_MISSING, f"The missing detail is: {label}", _missing_template(label)


async def ask_for_missing(state: PlanningAgentState) -> dict:
    """Ask about the single outstanding item this turn."""
    question = next_question(state)
    if question is None:
        # Defensive: the router should never route here with nothing to ask.
        return {}

    # What the agent is actually asking for, which is the narrower and more useful
    # half of "what does it still need": `next_question` picks one item, conflicts
    # before gaps, so this names the thing blocking progress right now rather than
    # the whole outstanding list. Only fires on turns that ask.
    logger.info(
        "audit.question_asked",
        extra=kv(
            kind=question["kind"],
            asked=question.get("label") or question["entry"].get("code"),
            outstanding=len(state.get("awaiting") or []),
        ),
    )

    system, user, fallback = _prompt(question)

    # The template carries every fact the question needs, options line included, so
    # handing it to the turn renderer loses nothing - see the module docstring.
    llm = None if get_settings().voice_enabled else get_llm()
    phrased = None

    if llm:
        try:
            response = await llm.ainvoke(
                [{"role": "system", "content": system}, {"role": "user", "content": user}]
            )
            phrased = (response.content or "").strip()
        except Exception:
            # A model outage must not break the flow - the template still works.
            phrased = None

    return {"messages": [{"role": "assistant", "content": phrased or fallback}]}
