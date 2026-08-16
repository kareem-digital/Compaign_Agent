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


def goals() -> list[dict]:
    """Campaign goals from the platform schema (v4.0 §4.8).

    Awareness is the default for CTV. Non-Awareness goals are valid but
    should be advised against — the agent advises, never blocks.
    """
    return list(_data().get("goals") or [])


def default_goal() -> dict | None:
    """The goal that is pre-filled for CTV (Awareness)."""
    return next((g for g in goals() if g.get("default")), None)


def kpis_for_goal(goal_value: str) -> list[dict]:
    """KPI options for a given goal value (e.g. 'AWARENESS' -> [Reach, Frequency]).

    Returns an empty list if the goal is unknown.
    Per schema v4.0 §4.8 and review comment 30: KPI list is conditional on goal.
    """
    kpi_map: dict = _data().get("kpis") or {}
    return list(kpi_map.get(goal_value.upper(), []))


def default_kpi(goal_value: str) -> dict | None:
    """The default KPI for a given goal (the one marked default: true)."""
    return next((k for k in kpis_for_goal(goal_value) if k.get("default")), None)
