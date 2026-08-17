"""The language model, and the choice to work without one.

Two jobs: understand a brief, and phrase what the agent says. Both degrade to
deterministic fallbacks when no API key is configured, which keeps tests and CI
free of secrets and means a missing key never takes the service down - it just
makes it less clever.

Everything the LLM produces is a *suggestion about the trader's own words*. It
never invents an ID, a price, or a forecast: those come from VOW via MCP. That
boundary is the zero-hallucination policy, and it is a boundary of architecture
rather than of prompting.

**Two clients, because the two jobs have different deadlines.** A turn is only
worth what the trader waits for it, and the browser stops waiting at 30 seconds
(`frontend/src/lib/config.ts`). Extraction is the parse - without it there is no
turn, so it may retry. Voicing is an enhancement with a deterministic fallback
sitting right behind it, so waiting twice for it is strictly worse than not
phrasing at all. That is why `get_voice_llm` never retries.

The clients were shared, on one 30-second timeout with two retries, and a turn
could spend 90 seconds on the optional half while the browser gave up at 30. See
`agent.voice` for the budget the two halves now divide.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import SecretStr

from app.config import get_settings

# Model families that spend tokens thinking before they answer, and accept a
# `reasoning_effort` to be told not to. Prefix-matched because the families are
# stable and the point releases are not - `gpt-5-mini`, `gpt-5.1`, `o3-mini` all
# belong here. A model outside the list is sent no such parameter, because one it
# does not recognise is a 400 rather than a hint.
_REASONING_FAMILIES = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    return model.lower().startswith(_REASONING_FAMILIES)


def _build(timeout: float, retries: int, reasoning_effort: str = ""):
    """A chat client on the given budget, or None when there is no model to build.

    Supports Anthropic (Claude) and OpenAI based on provider or configured keys.
    """
    settings = get_settings()

    provider = (settings.llm_provider or "").lower().strip()
    if provider == "openai":
        if not settings.openai_api_key:
            return None
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            return None
        extra: dict[str, Any] = {}
        if reasoning_effort and _is_reasoning_model(settings.llm_model):
            extra["reasoning_effort"] = reasoning_effort
        return ChatOpenAI(
            model=settings.llm_model or "gpt-4o-mini",
            temperature=settings.llm_temperature,
            api_key=SecretStr(settings.openai_api_key),
            timeout=timeout,
            max_retries=retries,
            **extra,
        )

    is_anthropic = (
        provider == "anthropic"
        or (settings.anthropic_api_key and not settings.openai_api_key)
        or (settings.llm_model.lower().startswith("claude") and settings.anthropic_api_key)
    )

    if is_anthropic and settings.anthropic_api_key:
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model_name=settings.llm_model or "claude-sonnet-4-5",
                anthropic_api_key=SecretStr(settings.anthropic_api_key),
                temperature=settings.llm_temperature,
                default_request_timeout=timeout,
                max_retries=retries,
            )
        except ImportError:
            pass

    if not settings.openai_api_key:
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    # `Any` rather than `str`: mypy checks a `**` splat against every remaining
    # parameter of the callee, so a concrete value type makes each one an error.
    extra: dict[str, Any] = {}
    if reasoning_effort and _is_reasoning_model(settings.llm_model):
        extra["reasoning_effort"] = reasoning_effort

    return ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=SecretStr(settings.openai_api_key),
        timeout=timeout,
        max_retries=retries,
        **extra,
    )


@lru_cache
def get_llm():
    """The chat model for understanding a brief, or None when no key is set.

    Cached: building the client each call would re-read config and re-create an
    HTTP pool on every message.
    """
    settings = get_settings()
    return _build(settings.llm_timeout_seconds, settings.llm_max_retries)


@lru_cache
def get_voice_llm():
    """The chat model for phrasing a turn, on a shorter leash and no retries.

    Deliberately a second client rather than an argument to `get_llm`: a retry
    policy is not a detail of a call site, it is a statement about whether the
    work is worth waiting for twice. Naming it keeps that decision visible - and
    keeps every `monkeypatch.setattr(..., "get_llm", lambda: None)` in the suite
    working unchanged.

    The reasoning budget is the other half. Re-voicing prose that has already been
    computed is not a reasoning task, and on `gpt-5-mini` the same call measured
    22.6s at the default and 5.5s told to keep effort low. Extraction keeps the
    default: reading a trader's brief is where thinking earns its latency.
    """
    settings = get_settings()
    return _build(
        settings.voice_timeout_seconds,
        retries=0,
        reasoning_effort=settings.voice_reasoning_effort,
    )
