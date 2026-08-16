"""Node 2 - present the CTV inventory available, by tier.

The tier is the primary fork in the whole flow: it decides whether reach can be
forecast, whether Amazon audiences apply, and whether the deal is even
selectable yet. Everything downstream branches on what this node writes.

The facts come from the grounded registry rather than from a raw MCP payload.
That moved three things out of this file: the provider-to-tier map (VOW's
`inventory-sources` tool now answers it, which is what the previous version of
this docstring asked for), the hand-written `external_deal_id` -> `deal_id`
mapping, and the double loop over the rate card's nested channels. What stays
here is presentation - how the inventory is described to a trader.

State still receives plain strings, not `Decimal` or enums: the checkpointer
serializes it, and `Decimal` is neither JSON-native nor safe in an f-string.

**Everything matching is offered; nothing is selected.** There is no
trader-facing selection step yet, so `selected_deals` means "available for this
plan", not "chosen". That is why the registry's `validate_deal_selection` is not
called here - on a plan carrying all inventory it would demand curation details
for the Disney+ portion on every campaign, and there is nowhere to put the
answer. `curation_requirements` on the state (schema v2 section 5, line 749) and
a `capture_curation_requirements` node (section 6, line 799) come first.

**A named provider narrows what is offered.** If the trader said "on Prime
Video", only Prime Video deals are kept: they told us, so asking again would be
a form rather than a conversation. Everything downstream then reflects what they
actually chose - the tier, the audience pricing, the forecast. `preferred_providers`
is what `extract_fields` read from the brief; `inventory_alternatives` records what
else this market carries, because a confirmation with no visible way out is an
announcement rather than a confirmation.
"""

from __future__ import annotations

import logging

from app.agent.gates import NO_INVENTORY, missing_basics, say
from app.agent.state import PlanningAgentState
from app.core.logging import kv
from app.knowledge.registry import AdvertiserRegistry, InventoryTierEnum
from app.knowledge.registry.models import TIER_LABELS, money_str
from app.knowledge.registry.validate import dominant_tier

logger = logging.getLogger(__name__)

STAGE = "inventory"

# Re-exported so `suggest_audiences` and `predict_reach` keep importing tier
# constants from the node they have always imported them from. They are the
# enum's values, so a comparison against either side agrees.
AMAZON_OWNED = InventoryTierEnum.AMAZON_OWNED.value
THIRD_PARTY_PRECURATED = InventoryTierEnum.THIRD_PARTY_PRECURATED.value
THIRD_PARTY_NEEDS_CURATION = InventoryTierEnum.THIRD_PARTY_NEEDS_CURATION.value


def _as_state(deal) -> dict:
    """One `DealItem` in the shape `PlanningAgentState.selected_deals` carries.

    Money goes out as a string. `state` is checkpointed as JSON, and a `Decimal`
    would both fail to serialize and render as `Decimal('18.22')` in the summary
    below.
    """
    return {
        "deal_id": deal.deal_id,
        "name": deal.name,
        "provider": deal.provider,
        "cpm": money_str(deal.cpm),
        "deal_type": deal.deal_type,
        "genre": deal.genre,
        "ad_lengths": list(deal.ad_lengths),
        "inventory_tier": deal.inventory_tier.value,
    }


def _markets_selling(data, durations: list[str], exclude: str) -> list[str]:
    """Loaded markets whose rate card prices every requested duration.

    Only markets already in the snapshot are considered - naming one whose
    inventory has never been fetched would be a guess, and the whole point of
    this message is that the alternatives it offers are real.
    """
    wanted = set(durations)
    return sorted(
        market
        for market in data.available_deals
        if market != exclude and wanted <= data.carried_durations(market)
    )


def _dead_end(data, market: str, durations: list[str], unavailable: list[str]) -> str:
    """Why nothing matched, and what would.

    Replaces "I could not find CTV inventory for {market}. Shall I widen the
    market or the durations?" - which was true, unhelpful, and left the trader
    guessing which of the two to change. Everything below comes off the snapshot
    the node already holds, so the alternatives are grounded rather than hopeful.

    Two dead ends the old message conflated, because they need opposite answers:
    the market sells nothing at all, or it sells nothing at this length.
    """
    carried = sorted(data.carried_durations(market), key=int)
    available = data.deals(market)

    if not available:
        elsewhere = sorted(m for m in data.available_deals if m != market)
        lines = [f"I have no CTV inventory at all for {market}."]
        if elsewhere:
            lines += ["", f"I do have inventory in {', '.join(elsewhere)}."]
        lines.append("Which market should I plan against?")
        return "\n".join(lines)

    # Deals exist; the requested lengths are what rules them out.
    asked = ", ".join(f"{d}s" for d in unavailable or durations)
    cheapest = min(available, key=lambda d: d.cpm)

    lines = []
    # `validate_basics` has already said this length is off the rate card - but
    # only when *every* requested length is. Where some are carried and some are
    # not, nothing has explained why the plan came back empty, so say it here.
    if not unavailable or set(unavailable) != set(durations):
        lines += [
            f"{market} does not sell {asked} CTV. The {market} rate card carries "
            f"{' and '.join(carried)} second.",
            "",
        ]

    lines += [
        "I can either:",
        f"- plan {market} with {' or '.join(f'{d}s' for d in carried)} - "
        f"{len(available)} deals, from {money_str(cheapest.cpm)} CPM",
    ]

    others = _markets_selling(data, durations, exclude=market)
    if others:
        lines.append(f"- keep {asked} and plan {' or '.join(others)} instead")
    else:
        lines.append(f"- keep {asked} and look at another market")

    lines += ["", "Which would you prefer?"]
    return "\n".join(lines)


def _no_such_provider(market: str, unavailable: list[str], alternatives: list[str]) -> str:
    """A named provider this market does not carry, and what it does carry.

    Precise beats generic: they asked for something specific and it is not sold
    here, so `_dead_end`'s "no inventory at all for GB" would read as a fault in
    the agent rather than an answer about the market. The alternatives come off
    the same snapshot, so what is offered is real.
    """
    others = ", ".join(alternatives) or "nothing else"
    return (
        f"{', '.join(unavailable)} isn't available in {market}. "
        f"{others} {'is' if len(alternatives) == 1 else 'are'} - shall I use that instead?"
    )


def _summary(deals: list[dict], market: str, preferred: list[str] | None = None) -> str:
    """The inventory on offer, headed by whether the trader narrowed it.

    Two openings, because the two situations need opposite wording: an unfiltered
    list is an offer ("here is what exists, choose"), and a filtered one is a
    confirmation ("you said Prime Video, here it is, say so if that is wrong").
    Presenting a confirmation as an offer is what makes an agent feel like a form.
    """
    if preferred:
        lines = [
            f"You've chosen {', '.join(preferred)}. Here are the deals available "
            f"in {market} - say if you'd like to change that.",
            "",
        ]
    else:
        lines = [f"CTV inventory available in {market}:", ""]

    for deal in deals:
        genre = f" | {deal['genre']}" if deal.get("genre") else ""
        lines.append(
            f"- {deal['provider']}{genre} - {deal['cpm']} CPM"
            f" ({', '.join(deal['ad_lengths'])}s) - "
            f"{TIER_LABELS[InventoryTierEnum(deal['inventory_tier'])]}"
        )

    # Genre upsell: the client asked for this explicitly. Only meaningful within
    # one provider, where the CPM difference buys a better contextual match.
    by_provider: dict[str, list[dict]] = {}
    for deal in deals:
        by_provider.setdefault(deal["provider"], []).append(deal)
    for provider, group in by_provider.items():
        base = next((d for d in group if not d.get("genre")), None)
        genred = [d for d in group if d.get("genre")]
        if base and genred:
            option = genred[0]
            lines += [
                "",
                f"{provider} run-of-service is {base['cpm']}; {option['genre']} is "
                f"{option['cpm']}. If the brief implies {option['genre']}, the higher "
                f"CPM usually buys a better match.",
            ]
            break

    return "\n".join(lines)


def make_select_inventory(registry: AdvertiserRegistry):
    """Build the node with its registry bound."""

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

        snapshot = await registry.snapshot(market)
        available = snapshot.data.deals(market)

        # The requested durations narrow what is offered; a deal that cannot run
        # the creative is not inventory for this plan.
        matching = [d for d in available if not durations or set(durations) & set(d.ad_lengths)]

        # A named provider narrows it further. Honoured rather than re-asked:
        # they told us, so everything downstream - the tier, the audience
        # pricing, the forecast - reflects what they actually chose.
        preferred = state.get("preferred_providers") or []
        if preferred:
            matching = [d for d in matching if d.provider in preferred]

        # Named a provider this market does not carry at all. Checked against
        # `available` rather than `matching`, so "Netflix, but not at 30s" stays a
        # duration dead end rather than being reported as a missing provider.
        unavailable_providers = [
            p for p in preferred if not any(d.provider == p for d in available)
        ]
        # What else the trader could switch to. A confirmation with no visible way
        # out is an announcement, not a confirmation.
        alternatives = sorted({d.provider for d in available if d.provider not in preferred})

        deals = [_as_state(d) for d in matching]
        # After both filters, so the tier describes the plan rather than the market.
        tier = dominant_tier(matching)

        # Which durations the market's rate card carries. Only used to explain a
        # dead end below - whether asking for an uncarried one is a *problem* is
        # `validate_basics`' answer to give, via the registry's
        # `validate_durations`. This node used to append its own string for that
        # too, which was a second implementation of the same check.
        carried = snapshot.data.carried_durations(market)
        unavailable = [d for d in durations if d not in carried]

        if deals:
            message = _summary(deals, market, preferred)
        elif unavailable_providers and alternatives:
            # The provider is the reason nothing matched, and the snapshot knows
            # what would - so say that rather than the market-wide dead end.
            message = _no_such_provider(market, unavailable_providers, alternatives)
        else:
            # The node knows exactly why nothing matched, so it says so here
            # rather than leaving it in `validation_errors` for nobody to read
            # and asking a vague question instead.
            message = _dead_end(snapshot.data, market, durations, unavailable)

        logger.info(
            "stage.inventory",
            extra=kv(
                market=market,
                deals=len(deals),
                dominant_tier=tier.value if tier else None,
                tiers=sorted({d["inventory_tier"] for d in deals}),
                preferred=preferred,
                filtered=bool(preferred),
            ),
        )
        logger.debug("stage.inventory.deals", extra=kv(deals=deals))

        if unavailable:
            # A plan that asks for something the market does not sell. Logged
            # only: `validate_basics` is what records it as a validation outcome,
            # via the registry's `validate_durations`.
            logger.warning(
                "inventory.duration_unavailable",
                extra=kv(market=market, requested=unavailable, carried=sorted(carried, key=int)),
            )

        if not deals:
            logger.warning(
                "inventory.none_found",
                extra=kv(
                    market=market,
                    durations=durations,
                    preferred=preferred,
                    unavailable_providers=unavailable_providers,
                ),
            )

        return {
            "current_stage": STAGE,
            # Records that this stage has run, so the next turn moves on.
            "stage_cursor": "inventory",
            "selected_deals": deals,
            "inventory_tier": tier.value if tier else None,
            # What this market carries that the trader did not name, so a UI can
            # offer the way out of a confirmation - see `presentation.inventory_block`.
            "inventory_alternatives": alternatives,
            # Nothing to plan against means stop, rather than suggest audiences
            # for inventory that does not exist. The question has already been
            # asked above, so the router ends the turn instead of routing to
            # `ask` - see `route_after_inventory`.
            "awaiting": [] if deals else [NO_INVENTORY],
            # `asking` on the dead end, because there the message *is* the turn's
            # question and the router sends it straight to END - suppressing a
            # repeat would end the turn saying nothing at all.
            **say(state, STAGE, message, asking=not deals),
        }

    return select_inventory
