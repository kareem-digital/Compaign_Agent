"""One turn, re-voiced - and the check that it is still the same turn.

The graph speaks in blocks. A single turn on a complete brief produces three of
them: what was understood, what inventory exists, what the audiences cost. Each is
correct, each is deterministic, and stacked together they read as a form rather
than as a colleague.

This module rewrites those blocks into one reply in the trader's voice. It runs at
the API boundary rather than inside a node, and that placement is the whole design:

**State stays deterministic.** `gates.say` suppresses a repeat by fingerprinting
the message a stage is about to emit. Model prose varies between calls, so a
digest taken over it would never match, `say` would never suppress anything, and
the loop that commit 09a613e removed would come straight back. Keeping the blocks
in `state["messages"]` byte-identical keeps that mechanism - and the audit trail,
the checkpointer's replay and the pinned conversation tests - exactly as they are.

**One call per turn, not one per node.** The persona's three-part shape is a
property of a *turn*, which a per-node rewrite could not produce: three nodes each
writing their own acknowledgement is three acknowledgements.

**It degrades to the blocks themselves.** No key, no model, a timeout, a refusal,
or output that fails the grounding check - every path returns the deterministic
join. The trader always gets the facts; the voice is what is optional.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

from app.agent.gates import digest
from app.agent.llm import get_voice_llm
from app.agent.prompts import turn_system_prompt
from app.config import get_settings
from app.core.logging import kv

logger = logging.getLogger(__name__)

# Any figure a trader could act on: a CPM, a fee, an impression count, a date
# part, a duration. Thousands separators are part of the token so that "2,472,799"
# is read as one number rather than as three.
_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Leading list markers - "1. ", "2) " - stripped before figures are counted. The
# model often renumbers or introduces a list, and an ordinal is not a claim about
# the plan. Without this the guard rejects good prose for saying "1.".
_LIST_MARKER = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)

# Padding allowance. Re-voicing adds connective tissue - an acknowledgement, a
# closing question - so some growth is expected; doubling is not. The floor keeps
# a one-line source from being held to a handful of characters.
_LENGTH_FACTOR = 1.6
_LENGTH_FLOOR = 200

# Below this a repeated line is punctuation or a short bullet, not a restated
# sentence - see `_duplicated`.
_DUPLICATE_MIN_CHARS = 25

# How much of each text a rejection keeps for diagnosis. A turn's prose runs to
# ~1500 characters, so this is most of it without turning a log line into a
# transcript.
_EVIDENCE_CHARS = 600


def _normalise(figure: str) -> str:
    """One number written every way the blocks write it, reduced to one string.

    Two normalisations, both learned from a live turn that was wrongly rejected:

      * commas out, because `extract_fields._confirmation` states "50000.00" and
        `deliver_plan._money` states "50,000" for the same budget;
      * trailing zeros off the fraction, because a model handed "50000.00" writes
        "50,000" - the same money, and the guard called it an invention.

    Only equal values are made equal. "18.22" survives intact, so a rewrite that
    rounds it to "18.2" is still caught.
    """
    figure = figure.replace(",", "")
    return figure.rstrip("0").rstrip(".") if "." in figure else figure


def _figures(text: str) -> set[str]:
    """Every actionable number in `text`, normalised for comparison."""
    counted = _LIST_MARKER.sub("", text)
    return {_normalise(match.group()) for match in _FIGURE.finditer(counted)}


def _duplicated(source: str, rendered: str) -> str | None:
    """A line the rewrite says twice and the source says once, if there is one.

    Substantial lines only. Blank lines and short fragments - a bullet reading
    "- Market: GB", a stray "and" - repeat legitimately, and treating them as
    duplication would reject prose for its punctuation.
    """
    seen: set[str] = set()

    for raw in rendered.splitlines():
        line = raw.strip()
        if len(line) < _DUPLICATE_MIN_CHARS:
            continue
        if line in seen and source.count(line) < 2:
            return line
        seen.add(line)

    return None


def _guard(source: str, rendered: str, providers: tuple[str, ...]) -> str | None:
    """Why `rendered` cannot be trusted, or None if it can.

    Three failures, in the order they matter. Each is a way the prose could have
    stopped being a rewrite and started being a claim.
    """
    if not rendered:
        return "empty"

    # 1. An invented figure. The one failure that puts a wrong price or a
    #    fabricated reach number in front of a trader, so it is checked first.
    invented = _figures(rendered) - _figures(source)
    if invented:
        return f"invented_figures:{','.join(sorted(invented)[:5])}"

    # 2. A dropped provider. Summarising four deals into "several options" loses
    #    the thing the trader is choosing between. Only providers the source
    #    actually names are required, so a turn where inventory did not speak is
    #    not held to a list it never had.
    dropped = [p for p in providers if p in source and p not in rendered]
    if dropped:
        return f"dropped_providers:{','.join(dropped[:5])}"

    # 3. A line said twice. The blocks were each written to stand alone, so the
    #    turn's question often appears in two of them - and a model told to
    #    reproduce the source faithfully will dutifully emit both. The first live
    #    run closed by asking for the audience choice, then asked again verbatim.
    #    Only lines the source itself says once are checked, because a genuinely
    #    repeated source line is the blocks' own doing and not the model's.
    repeated = _duplicated(source, rendered)
    if repeated:
        return f"repeated_line:{repeated[:60]}"

    # 4. Padding. Cheap proxy for the failure that has no other signature -
    #    invented next steps, restated caveats, an essay where a line was asked
    #    for - and the reason the prompt states a length rule at all.
    if len(rendered) > max(_LENGTH_FLOOR, int(len(source) * _LENGTH_FACTOR)):
        return f"too_long:{len(rendered)}v{len(source)}"

    return None


def _user_prompt(source: str, trader_message: str) -> str:
    """What the model is given: the trader's words, then the facts to re-voice.

    The stage used to be in here as context. It came back out in the trader's
    reply - "Plan is at delivered stage and ready to be pushed" - which is the
    language of software in a message about a media plan, and precisely what the
    persona bans. A name the model is never given is a name it cannot leak, so
    `stage` stays what it always was: a log field.
    """
    return "\n\n".join(
        (
            f"The trader's latest message:\n{trader_message}",
            f"The material to re-voice, in order:\n\n{source}",
        )
    )


async def render_turn(
    blocks: list[str],
    *,
    trader_message: str,
    stage: str | None = None,
    providers: tuple[str, ...] = (),
) -> str:
    """The turn's blocks as one reply in the agent's voice, or joined verbatim.

    `providers` comes from `selected_deals` rather than from a regex over the
    prose: the names worth protecting are the ones the graph actually planned
    against, and deriving them from state means the check cannot drift from what
    inventory the plan holds.
    """
    source = "\n\n".join(block for block in blocks if block)

    settings = get_settings()
    llm = get_voice_llm() if settings.voice_enabled else None

    if llm is None:
        # Not an error, and logged at debug: running without a key is a supported
        # configuration, and this fires on every turn in CI.
        # logger.debug("voice.skipped", extra=kv(reason="disabled_or_no_llm", stage=stage))
        return source

    started = time.monotonic()

    try:
        # Wall clock, not the client's HTTP timeout. That one governs the request;
        # this one governs the turn, and the turn is what the browser is waiting
        # on. Without it a slow connect or a stalled stream spends the whole
        # budget and the trader is told the agent could not be reached - which is
        # exactly what happened, on a backend that was working perfectly.
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    {"role": "system", "content": turn_system_prompt()},
                    {"role": "user", "content": _user_prompt(source, trader_message)},
                ]
            ),
            timeout=settings.voice_timeout_seconds,
        )
        rendered = (response.content or "").strip()
    except TimeoutError:
        # Its own event, because "too slow" and "it broke" want different answers:
        # this one is a budget to re-tune, not an outage to investigate.
        logger.warning(
            "voice.timeout",
            extra=kv(
                stage=stage,
                budget_seconds=settings.voice_timeout_seconds,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            ),
        )
        return source
    except Exception:
        # A model outage must not cost the trader their plan. Same discipline as
        # `ask_for_missing`: the deterministic text was always going to be there.
        logger.warning("voice.failed", extra=kv(stage=stage), exc_info=True)
        return source

    elapsed_ms = int((time.monotonic() - started) * 1000)
    refused = _guard(source, rendered, providers)

    if refused:
        logger.warning(
            "voice.rejected",
            extra=kv(reason=refused, stage=stage, source=digest(source), elapsed_ms=elapsed_ms),
        )
        # The texts, one level down. The first rejections in production were
        # undiagnosable because only the digest was kept: "invented_figures:18.22"
        # names the token and not the sentence it came from, and the pair cannot be
        # reconstructed afterwards. Truncated, and at DEBUG, because this is the
        # whole turn's prose and it belongs in an investigation rather than in the
        # running log.
        logger.debug(
            "voice.rejected.evidence",
            extra=kv(
                reason=refused,
                source_text=source[:_EVIDENCE_CHARS],
                rendered_text=rendered[:_EVIDENCE_CHARS],
            ),
        )
        return source

    # Both digests, so an audit can tie what the trader read to the facts the
    # graph computed - the rendered text is deliberately not checkpointed, and
    # this pair is the only record that the two correspond.
    # logger.info(
    #     "voice.rendered",
    #     extra=kv(
    #         stage=stage,
    #         source=digest(source),
    #         rendered=digest(rendered),
    #         source_len=len(source),
    #         rendered_len=len(rendered),
    #         elapsed_ms=elapsed_ms,
    #     ),
    # )
    return rendered
