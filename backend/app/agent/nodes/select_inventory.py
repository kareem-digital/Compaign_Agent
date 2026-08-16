"""Node 2 - fetch CTV deals and classify them into the three inventory tiers.

The tier is the primary fork in the whole flow: it decides whether reach can be
forecast, whether Amazon audiences apply, and whether the deal is even
selectable yet. Everything downstream branches on what this node writes.

Provider-to-tier mapping comes from `app.knowledge.reference`, one source
shared with extraction. When VOW's MCP server returns the tier itself, that
lookup goes away and we trust the server.

If the trader named providers, only those are kept: they told us, so asking
again would be a form rather than a conversation.
"""

from __future__ import annotations

import logging

from app.agent.gates import NO_INVENTORY, missing_basics
from app.agent.state import PlanningAgentState
from app.core.logging import kv
from app.knowledge import reference
from app.tools.mcp import MCPClient, VowTools

logger = logging.getLogger(__name__)

STAGE = "inventory"

AMAZON_OWNED = "AMAZON_OWNED"
THIRD_PARTY_PRECURATED = "THIRD_PARTY_PRECURATED"
THIRD_PARTY_NEEDS_CURATION = "THIRD_PARTY_NEEDS_CURATION"

_TIER_LABEL = {
    AMAZON_OWNED: "Amazon-owned (reach forecast available)",
    THIRD_PARTY_PRECURATED: "third-party, pre-curated (no reach forecast)",
    THIRD_PARTY_NEEDS_CURATION: "third-party, needs curation (rate card only)",
}


def classify_tier(provider: str) -> str:
    """Map a provider name to its inventory tier.

    Unknown providers are treated as needing curation - the most conservative
    tier, since it promises the least. Guessing that something is Amazon-owned
    would let a reach forecast be attempted on inventory that has none.
    """
    return reference.tier_for_provider(provider) or THIRD_PARTY_NEEDS_CURATION


def dominant_tier(deals: list[dict]) -> str | None:
    """The tier that governs downstream branching.

    Amazon wins when present, because it is the only tier that unlocks
    forecasting and the repair loop. A mixed plan is handled per-portion later;
    for now this records which capabilities are in play at all.
    """
    tiers = {deal["inventory_tier"] for deal in deals}
    for tier in (AMAZON_OWNED, THIRD_PARTY_PRECURATED, THIRD_PARTY_NEEDS_CURATION):
        if tier in tiers:
            return tier
    return None


def _summary(
    deals: list[dict],
    market: str,
    preferred: list[str] | None = None,
    unavailable_providers: list[str] | None = None,
    alternatives: list[str] | None = None,
) -> str:
    preferred = preferred or []
    unavailable_providers = unavailable_providers or []

    if unavailable_providers and not deals:
        # Precise beats generic: they asked for something specific and it is not
        # sold here. Saying "no inventory found" would look like a fault.
        others = ", ".join(alternatives or []) or "nothing else"
        return (
            f"{', '.join(unavailable_providers)} isn't available in {market}. "
            f"{others} {'is' if len(alternatives or []) == 1 else 'are'} - "
            "shall I use that instead?"
        )

    if not deals:
        return f"I could not find CTV inventory for {market}. Shall I widen the market or the durations?"

    if preferred:
        return f"You've chosen {', '.join(preferred)}. Here are the deals available in {market} — say if you'd like to change that."
    return f"Here is the available CTV inventory in {market}. Which inventory would you like to select for your campaign?"


def make_select_inventory(mcp: MCPClient):
    """Build the node with its MCP client bound."""

    async def select_inventory(state: PlanningAgentState) -> dict:
        markets = state.get("markets") or []
        if not markets:
            # The basics gate should have stopped the graph before here.
            # Defensive only, and it still refuses rather than guessing.
            return {
                "current_stage": STAGE,
                "selected_deals": [],
                "awaiting": missing_basics(state),
            }

        market = markets[0]
        durations = state.get("durations") or []

        response = await mcp.call_tool(
            VowTools.LIST_DEALS,
            {"market": market, "format": "streaming_tv", "durations": durations},
        )
        rate_card = await mcp.call_tool(VowTools.CTV_RATE_CARD, {"market": market})

        available = [
            {
                "deal_id": raw["external_deal_id"],
                "name": raw["name"],
                "provider": raw["provider"],
                "cpm": raw["deal_price_amount"],
                "deal_type": raw["deal_type"],
                "genre": raw.get("genre"),
                "ad_lengths": raw.get("ad_lengths", []),
                "inventory_tier": classify_tier(raw["provider"]),
            }
            for raw in response.get("results", [])
        ]

        # If the trader already named providers, honour that rather than
        # offering everything: they told us, so asking again is not a
        # conversation, it is a form. Everything downstream then reflects what
        # they actually chose - the tier, the audience pricing, the forecast.
        preferred = state.get("preferred_providers") or []
        deals = [d for d in available if d["provider"] in preferred] if preferred else available

        # Named a provider this market does not carry. Worth saying precisely
        # what happened, because "no inventory found" would read as a bug.
        unavailable_providers = [
            p for p in preferred if not any(d["provider"] == p for d in available)
        ]

        tier = dominant_tier(deals)

        # The rate card is the authority on which durations a market actually
        # sells. Asking for one that isn't carried is a planning error worth
        # catching here rather than at strategy creation.
        carried = {
            entry["duration"]
            for channel in rate_card.get("channels", [])
            for entry in channel.get("durations", [])
        }
        unavailable = [d for d in durations if d not in carried]

        logger.info(
            "stage.inventory",
            extra=kv(
                market=market,
                deals=len(deals),
                dominant_tier=tier,
                tiers={d["inventory_tier"] for d in deals},
                preferred=preferred,
                filtered=bool(preferred),
            ),
        )
        logger.debug("stage.inventory.deals", extra=kv(deals=deals))

        errors = list(state.get("validation_errors") or [])
        if unavailable:
            # A plan that asks for something the market does not sell.
            logger.warning(
                "inventory.duration_unavailable",
                extra=kv(market=market, requested=unavailable, carried=sorted(carried)),
            )
            errors.append(f"durations not on the {market} rate card: {', '.join(unavailable)}")

        if not deals:
            logger.warning(
                "inventory.none_found",
                extra=kv(market=market, durations=durations, preferred=preferred),
            )

        # What else the trader could switch to. A confirmation with no visible
        # way out is an announcement, not a confirmation.
        alternatives = sorted({d["provider"] for d in available if d["provider"] not in preferred})

        return {
            "current_stage": STAGE,
            # Records that this stage has run, so the next turn moves on.
            "stage_cursor": "inventory",
            "selected_deals": deals,
            "inventory_alternatives": alternatives,
            "inventory_tier": tier,
            "validation_errors": errors,
            # Nothing to plan against means stop and ask, rather than suggest
            # audiences for inventory that does not exist.
            "awaiting": [] if deals else [NO_INVENTORY],
            "messages": [
                {
                    "role": "assistant",
                    "content": _summary(
                        deals, market, preferred, unavailable_providers, alternatives
                    ),
                }
            ],
        }

    return select_inventory
