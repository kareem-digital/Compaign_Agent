"""The language model, and the choice to work without one.

Two jobs: understand a brief, and phrase a follow-up question. Both degrade to
deterministic fallbacks when no API key is configured, which keeps tests and CI
free of secrets and means a missing key never takes the service down - it just
makes it less clever.

Everything the LLM produces is a *suggestion about the trader's own words*. It
never invents an ID, a price, or a forecast: those come from VOW via MCP. That
boundary is the zero-hallucination policy, and it is a boundary of architecture
rather than of prompting.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings
from app.core.logging import kv

logger = logging.getLogger(__name__)


def log_usage(label: str, raw_message, duration_ms: int) -> None:
    """Record what one model call cost.

    Every turn now spends money. Without tokens in the log the first sign of a
    runaway prompt is the invoice.
    """
    usage = getattr(raw_message, "usage_metadata", None) or {}
    logger.info(
        "llm.call",
        extra=kv(
            purpose=label,
            model=get_settings().llm_model,
            tokens_in=usage.get("input_tokens"),
            tokens_out=usage.get("output_tokens"),
            duration_ms=duration_ms,
        ),
    )


@lru_cache
def get_llm():
    """The configured chat model, or None when no key is set.

    Cached: building the client each call would re-read config and re-create an
    HTTP pool on every message.
    """
    settings = get_settings()

    if not settings.openai_api_key:
        logger.info("No OPENAI_API_KEY set - using pattern matching instead of an LLM.")
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning(
            "OPENAI_API_KEY is set but langchain-openai is not installed. "
            "Run: pip install -r requirements.txt. Falling back to pattern matching."
        )
        return None

    logger.info("Using %s for brief understanding.", settings.llm_model)
    return ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key,
        timeout=30,
        max_retries=2,
    )
