"""Node 3 - always offer three audience options: narrow, balanced, wide.

Audiences are mandatory and suggestion-driven. Nobody browses VOW's ~3,400
segments by hand, so the agent asks the server to suggest and then presents
exactly three shapes.

The number that matters is the **effective CPM** - deal CPM plus the audience
VCPM fee. A narrow audience is both smaller and dearer per impression, so
showing the deal price alone understates what precision costs. Surfacing the
combined figure per option is the whole point of this node.

Amazon audiences apply only to Amazon-owned inventory; for third-party the
provider's own targeting applies and adds its own CPM. That is stated rather
than silently ignored.
"""

from __future__ import annotations

import logging

from app.agent.gates import NO_AUDIENCE
from app.agent.nodes.select_inventory import AMAZON_OWNED
from app.agent.state import PlanningAgentState
from app.core.logging import kv
from app.tools.mcp import MCPClient, VowTools

logger = logging.getLogger(__name__)

STAGE = "audiences"

_PROFILE_ORDER = ("NARROW", "BALANCED", "WIDE")

_PROFILE_NOTE = {
    "NARROW": "highest intent, smallest pool, highest fee - underdelivery risk",
    "BALANCED": "the usual recommendation",
    "WIDE": "widest reach, lowest fee, least precision",
}


def _cheapest_amazon_cpm(deals: list[dict]) -> float | None:
    """Base CPM the audience fee stacks onto.

    Cheapest Amazon deal rather than an average: the fee applies per
    impression, and the trader will optimise toward the cheapest qualifying
    inventory, so that is the honest anchor.
    """
    amazon_cpms = [
        float(deal["cpm"])
        for deal in deals
        if deal.get("inventory_tier") == AMAZON_OWNED and deal.get("cpm")
    ]
    return min(amazon_cpms) if amazon_cpms else None


def _summary(options: list[dict], has_amazon: bool, has_third_party: bool) -> str:
    lines = ["Three audience options - pick one and I will forecast against it.", ""]

    for option in options:
        effective = option.get("effective_cpm")
        price = (
            f"{option['cpm_basis']} + {option['vcpm_fee']} fee = {effective} effective CPM"
            if effective
            else f"{option['vcpm_fee']} fee (no Amazon inventory to price against)"
        )
        lines += [
            f"**{option['profile'].title()}** - {option['name']}",
            f"  {option['segment_count']} segments, ~{option['estimated_size']:,} people",
            f"  {price}",
            f"  {_PROFILE_NOTE[option['profile']]}",
            "",
        ]

    if has_third_party:
        note = (
            "Amazon audiences apply to the Prime Video portion only. "
            "Netflix and Disney+ use their own targeting, which adds their own CPM."
        )
        lines.append(
            note
            if has_amazon
            else "Note: this plan has no Amazon inventory, so Amazon audiences do not "
            "apply at all - the providers' own targeting governs."
        )

    return "\n".join(lines).rstrip()


def make_suggest_audiences(mcp: MCPClient):
    """Build the node with its MCP client bound."""

    async def suggest_audiences(state: PlanningAgentState) -> dict:
        deals = state.get("selected_deals") or []
        markets = state.get("markets") or []

        response = await mcp.call_tool(
            VowTools.SUGGEST_AUDIENCES,
            {
                "market": markets[0] if markets else None,
                "goal": state.get("goal", "AWARENESS"),
                "brief": state.get("strategy_name"),
            },
        )

        base_cpm = _cheapest_amazon_cpm(deals)
        suggestions = {s["profile"]: s for s in response.get("suggestions", [])}

        options = []
        for profile in _PROFILE_ORDER:
            suggestion = suggestions.get(profile)
            if not suggestion:
                continue

            fee = float(suggestion["vcpm_fee"])
            option = {
                "audience_set_id": suggestion["audience_set_id"],
                "name": suggestion["name"],
                "profile": profile,
                "vcpm_fee": suggestion["vcpm_fee"],
                "segment_count": suggestion["segment_count"],
                "estimated_size": suggestion["estimated_size"],
                "cpm_basis": f"{base_cpm:.2f}" if base_cpm else None,
                "effective_cpm": f"{base_cpm + fee:.2f}" if base_cpm else None,
            }
            options.append(option)

        missing = [p for p in _PROFILE_ORDER if p not in suggestions]
        errors = list(state.get("validation_errors") or [])
        if missing:
            # Three options are mandatory; fewer is a server-contract problem,
            # so this points at VOW rather than at the plan.
            logger.warning(
                "audiences.incomplete_profiles",
                extra=kv(missing=missing, returned=sorted(suggestions)),
            )
            errors.append(f"audience suggestion returned no {', '.join(missing)} profile")

        tiers = {deal.get("inventory_tier") for deal in deals}
        logger.info(
            "stage.audiences",
            extra=kv(
                options=len(options),
                base_cpm=base_cpm,
                priced=bool(base_cpm),
                chosen="BALANCED" if options else None,
            ),
        )
        logger.debug("stage.audiences.options", extra=kv(options=options))

        return {
            "current_stage": STAGE,
            "stage_cursor": "audiences",
            "audience_options": options,
            # No audience means nothing to forecast against.
            "awaiting": [] if options else [NO_AUDIENCE],
            # Balanced is the documented default recommendation. The trader
            # confirms or changes it at approval; nothing is locked here.
            "chosen_audience": next(
                (o for o in options if o["profile"] == "BALANCED"), options[0] if options else None
            ),
            "validation_errors": errors,
            "messages": [
                {
                    "role": "assistant",
                    "content": _summary(
                        options,
                        has_amazon=AMAZON_OWNED in tiers,
                        has_third_party=bool(tiers - {AMAZON_OWNED}),
                    ),
                }
            ],
        }

    return suggest_audiences
