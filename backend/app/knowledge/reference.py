"""Reference values from VOW's platform, behind a stable interface.

Callers ask a function, never a file:

    reference.markets()      -> [{"value": "GB", "label": "United Kingdom", ...}, ...]
    reference.durations()    -> ["10", "15", "20", "30"]

TMP-22: loaded from a local YAML file today. These are facts about VOW, so they
belong in VOW - via MCP once the server exists, or the database once we have
access. When that happens, only this module changes; every caller is unaffected.

Converges with KNW-01, the grounded registry. That handles thousands of entity
records; this handles a handful of enumerations. To be reconciled with Vishal
rather than left as two registries.
"""

import re
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.exceptions import ConfigurationError

DATA_PATH = Path(__file__).parent / "reference_data.yaml"


@lru_cache
def _data() -> dict:
    """Parsed once per process.

    Fails closed - offering the wrong markets is worse than not starting,
    because a user would pick one and be refused later by governance, which is
    a dead end we led them into.
    """
    try:
        return yaml.safe_load(DATA_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ConfigurationError(
            f"Reference data could not be loaded from {DATA_PATH}: {exc}"
        ) from exc


def markets() -> list[dict]:
    """Markets VOW sells in, as selectable options."""
    return list(_data().get("markets") or [])


def market_codes() -> list[str]:
    """Just the ISO codes. This is the list the governance policy duplicates."""
    return [m["value"] for m in markets()]


def durations() -> list[str]:
    """Creative lengths VOW sells, in seconds."""
    return list(_data().get("durations") or [])


def inventory_tiers() -> list[dict]:
    """The three tiers, with what each one can and cannot do."""
    return list(_data().get("inventory_tiers") or [])


def providers() -> list[dict]:
    """CTV providers, as selectable options."""
    return list(_data().get("providers") or [])


def provider_from_text(text: str) -> list[str]:
    """Which providers a sentence mentions, in the order they are listed.

    Matched on word boundaries so "prime" inside another word cannot trigger,
    and longest alias first so "amazon prime" resolves before "amazon".
    """
    lowered = (text or "").lower()
    found = []

    for provider in providers():
        aliases = sorted(provider.get("aliases") or [], key=len, reverse=True)
        for alias in aliases:
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered):
                found.append(provider["value"])
                break

    return found


def tier_for_provider(name: str) -> str | None:
    """The inventory tier a provider belongs to, or None if we don't know it.

    None matters: an unknown provider must not be assumed Amazon-owned, because
    that tier is the only one that unlocks reach forecasting.
    """
    target = (name or "").strip().lower()
    return next(
        (p.get("tier") for p in providers() if p["value"].strip().lower() == target),
        None,
    )


def currency_for(market: str) -> str | None:
    """The currency a market trades in, or None if we don't sell there."""
    return next((m.get("currency") for m in markets() if m["value"] == market), None)


def age_groups() -> list[str]:
    """Standard demographic age cohorts."""
    return ["18-24", "25-34", "35-44", "45-54", "55+"]


def genders() -> list[str]:
    """Gender options."""
    return ["Female", "Male", "All"]


def household_incomes(market: str = "GB") -> list[str]:
    """Household income tiers."""
    if market == "US":
        return ["$50-75k", "$75-100k", "$100k+"]
    return ["£35-55k", "£55-80k", "£80k+"]


def household_types() -> list[str]:
    """Household composition types."""
    return ["Families with children", "Couples", "Single Person Households"]


def device_types() -> list[dict]:
    """Supported CTV device types."""
    return [
        {"value": "CONNECTED_TV", "label": "Smart TV", "required": True},
        {"value": "STREAMING_STICK", "label": "Fire TV / Streaming Stick"},
        {"value": "GAMES_CONSOLE", "label": "Games Console"},
    ]


def interest_categories() -> list[str]:
    """In-market and lifestyle interest categories."""
    return [
        "Green / Environmentally Conscious",
        "Health & Wellness",
        "Organic & Natural Food Buyers",
        "Runners & Fitness",
        "Tech Enthusiasts",
        "Entertainment & Gaming",
    ]

