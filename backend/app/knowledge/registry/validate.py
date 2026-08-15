"""Two kinds of validation, and the flow's money.

They are separate classes because they answer different questions.

**`SnapshotValidator` runs at ingest time and gates the registry update.** Its
question is "can this reference data be trusted?" - required fields present,
types right, references resolving, and how the incoming shape compares with the
last one we accepted. Its failures are about VOW, not about the trader, so they
raise `RegistryValidationError` or land on the snapshot's `meta`. It never raises
`GroundingError`.

**`StepwiseCTVValidator` runs during the conversation.** Its question is "is what
the trader asked for something VOW can actually do?" - and its answers are prose
the agent can say out loud. `gates.py` sets the standard: requirements are
described in the trader's language, because these strings become the question the
agent asks.

**Pricing lives here too**, at module level, because effective CPM is the flow's
headline number (section 2.4, section 3 step 4) and it should have exactly one
implementation. `suggest_audiences` calls these rather than keeping its own copy,
and the arithmetic is `Decimal` throughout - the float version it replaced could
not represent `18.22 + 3.50` exactly.

The soft/hard split: everything here returns `ValidationResponse` so the agent
can *say* "not that, try one of these". `assert_grounded` at the bottom is the
only place that raises `GroundingError`, and it should be called where proceeding
is unacceptable - anywhere a deal ID or audience set ID is about to be sent to
VOW.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.exceptions import GroundingError, RegistryValidationError
from app.core.logging import kv
from app.knowledge.registry.models import (
    CTV_KPIS,
    CURRENCY_BY_MARKET,
    MONEY,
    TIER_LABELS,
    TIER_PRECEDENCE,
    Compatibility,
    DealItem,
    GroundedRegistryData,
    GroundedRegistrySnapshot,
    InventoryTierEnum,
    NormalizationError,
    RegistryDiff,
    RegistrySnapshotMeta,
    ValidationResponse,
    duration_phrase,
    money_str,
    normalize_currency,
    normalize_duration,
    normalize_goal,
    normalize_kpi,
    normalize_market,
    normalize_matching_mode,
    normalize_profile,
    normalize_split_method,
    to_money,
)

logger = logging.getLogger(__name__)

# So `validate_payload(DealItem, ...)` is typed as returning a DealItem rather
# than a bare BaseModel - the callers immediately read model-specific fields.
_M = TypeVar("_M", bound=BaseModel)

# The five things VOW needs in order to curate a third-party deal later -
# section 3 step 2, "Curation capture".
CURATION_FIELDS = ("genres", "durations", "targeting_preferences", "budget", "flight_dates")

# Where a changed *value* is expected rather than alarming. Deal prices and
# audience fees move; a tier assignment or an enum membership changing is a
# different event entirely. Without this split, a routine price update would
# classify as a breaking change and the alarm would be ignored within a week.
VALUE_CHURN_SEGMENTS = ("cpm", "vcpm_fee", "estimated_size", "segment_count", "name")


# --- pricing -----------------------------------------------------------------


def calculate_effective_cpm(deal_cpm: Decimal, vcpm_fee: Decimal) -> Decimal:
    """Deal CPM plus the audience VCPM fee - what the trader actually pays.

    Section 2.4: the fee stacks on top of the deal price, so a narrow audience is
    both smaller and dearer per impression. Showing the deal price alone
    understates what precision costs, which is why this number exists.

    `Decimal` throughout: `18.22 + 3.50` as floats is not `21.72`, and a trader
    commits budget against this figure.
    """
    return (to_money(deal_cpm) + to_money(vcpm_fee)).quantize(MONEY, rounding=ROUND_HALF_UP)


def cheapest_amazon_cpm(deals: list[DealItem] | tuple[DealItem, ...]) -> Decimal | None:
    """The base CPM an audience fee stacks onto, or None if there is no Amazon deal.

    Cheapest Amazon deal rather than an average: the fee applies per impression
    and the trader will optimise toward the cheapest qualifying inventory, so that
    is the honest anchor. `None` rather than zero when there is no Amazon
    inventory - Amazon audiences do not apply to third-party inventory at all,
    and a zero would read as "free".
    """
    cpms = [deal.cpm for deal in deals if deal.supports_reach_forecast]
    return min(cpms) if cpms else None


def dominant_tier(deals: list[DealItem] | tuple[DealItem, ...]) -> InventoryTierEnum | None:
    """The tier that governs what the flow can promise about a selection.

    Amazon wins when present, because it is the only tier that unlocks
    forecasting and the repair loop. A mixed plan is handled per-portion
    downstream; this records which capabilities are in play at all.
    """
    tiers = {deal.inventory_tier for deal in deals}
    return next((tier for tier in TIER_PRECEDENCE if tier in tiers), None)


def impressions_for(budget: Decimal, cpm: Decimal) -> int:
    """budget / CPM x 1000. Used by the budget split and by the honesty rule.

    Section 3 step 6 requires this for third-party inventory, where impressions
    are all that can honestly be derived. Defined once so step 3 and step 6
    cannot disagree.
    """
    cpm = to_money(cpm)
    if cpm <= 0:
        return 0
    return int((to_money(budget) / cpm) * 1000)


# --- checks that need no grounded data ---------------------------------------
#
# Module level rather than methods, because they ask nothing of the snapshot. A
# node with no registry bound - `extract_fields` runs before a market is even
# known - can still call them, which is the point.


def check_flight_dates(flight_dates: dict | None, today: date | None = None) -> ValidationResponse:
    """Section 3 step 1: `lower` no earlier than today, `upper` after `lower`.

    Worth checking because `extract_fields._flight_dates` will happily read
    "August" as a month that has already passed - the pattern matcher has no
    notion of "already".

    `today` is injectable so a test is not time-dependent.
    """
    today = today or date.today()

    if not flight_dates or not flight_dates.get("lower") or not flight_dates.get("upper"):
        return ValidationResponse(
            is_valid=False,
            code="flight_dates.missing",
            field="flight_dates",
            message="What are the campaign start and end dates?",
        )

    try:
        lower = date.fromisoformat(str(flight_dates["lower"]))
        upper = date.fromisoformat(str(flight_dates["upper"]))
    except ValueError:
        return ValidationResponse(
            is_valid=False,
            code="flight_dates.unparseable",
            field="flight_dates",
            message="I could not read those dates. Could you give them as YYYY-MM-DD?",
        )

    if lower < today:
        return ValidationResponse(
            is_valid=False,
            code="flight_dates.in_past",
            field="flight_dates",
            message=(
                f"the flight starts {lower.isoformat()}, which has already passed - "
                f"a campaign cannot run from a date in the past"
            ),
            metadata={"today": today.isoformat()},
        )

    if upper <= lower:
        return ValidationResponse(
            is_valid=False,
            code="flight_dates.inverted",
            field="flight_dates",
            message=(
                f"the end date {upper.isoformat()} is not after the start {lower.isoformat()}"
            ),
        )

    return _ok(
        f"Flight {lower.isoformat()} to {upper.isoformat()}.",
        code="flight_dates.ok",
        field="flight_dates",
        metadata={"days": (upper - lower).days},
    )


def check_forecast_shape(payload: dict) -> ValidationResponse:
    """Refuse a forecast that claims unavailable and then supplies reach.

    Section 3 step 6: "Never invent a reach number." A payload saying
    `is_available: false` while carrying `estimated_unique_reach` is exactly the
    fabricated-reach failure mode, so it is caught structurally rather than left
    to whichever node happens to read the field.
    """
    if "is_available" not in payload:
        return ValidationResponse(
            is_valid=False,
            code="forecast.no_availability_flag",
            field="forecast",
            message="the forecast did not say whether reach is available for this inventory",
        )

    if payload.get("is_available"):
        missing = [
            key
            for key in ("estimated_impressions", "estimated_unique_reach", "average_frequency")
            if payload.get(key) is None
        ]
        if missing:
            return ValidationResponse(
                is_valid=False,
                code="forecast.incomplete",
                field="forecast",
                message=f"the forecast claims reach is available but omits {', '.join(missing)}",
            )
        return _ok("Forecast is complete.", code="forecast.ok", field="forecast")

    fabricated = [
        key
        for key in ("estimated_unique_reach", "average_frequency", "reach_curve")
        if payload.get(key) is not None
    ]
    if fabricated:
        return ValidationResponse(
            is_valid=False,
            code="forecast.fabricated_reach",
            field="forecast",
            message=(
                f"the forecast says reach is unavailable but supplied "
                f"{', '.join(fabricated)} - I will not report that as reach"
            ),
            metadata={"fabricated_fields": fabricated},
        )

    return _ok(
        "Forecast is unavailable for this inventory, and says so honestly.",
        code="forecast.unavailable_ok",
        field="forecast",
        metadata={"reach_available": False},
    )


# --- ingest-time validation --------------------------------------------------


class SnapshotValidator:
    """Gates a registry update. Nothing enters a snapshot without passing here."""

    def validate_payload(self, model: type[_M], payload: dict, label: str) -> _M:
        """Parse one item, and say something when the shape drifts.

        Two branches, which is the whole additive-vs-breaking distinction without
        a compatibility engine behind it:

          * a missing or mistyped **required** field is breaking, so it raises
            and names the tool - a `KeyError` three layers down in a graph node
            is unattributable, which is the failure mode this replaces;
          * **unknown extra** keys are additive, so they warn once and are
            dropped. The server growing a field must not stop the flow.
        """
        try:
            parsed = model.model_validate(payload)
        except Exception as exc:
            raise RegistryValidationError(
                f"{label} returned an item this registry cannot read: {exc}",
                violations=[f"{label}: {exc}"],
            ) from exc

        known = set(model.model_fields)
        aliases = {
            alias
            for field in model.model_fields.values()
            for alias in getattr(field.validation_alias, "choices", []) or []
        }
        unknown = set(payload) - known - {str(a) for a in aliases}
        if unknown:
            logger.warning(
                "registry.unknown_fields",
                extra=kv(source=label, fields=sorted(unknown), action="ignored"),
            )

        return parsed

    def check_required_facets(self, data: GroundedRegistryData) -> list[str]:
        """Facets without which the flow genuinely cannot run.

        Half a snapshot is worse than none: a node grounding against an empty
        market set would reject every market the trader names.
        """
        violations = []

        if not data.valid_markets:
            violations.append("no valid markets - step 1 cannot ground a target market")
        if not data.valid_durations:
            violations.append("no valid durations - step 1 cannot ground a creative length")

        # Section 3 step 4: three options, always. Fewer is a server-contract
        # problem, and the audience step has no meaning without all three.
        missing = [
            profile
            for profile in ("NARROW", "BALANCED", "WIDE")
            if profile not in data.audience_profiles
        ]
        if missing:
            violations.append(
                f"audience profiles {missing} missing - step 4 requires all three options"
            )

        return violations

    def check_referential_integrity(
        self, data: GroundedRegistryData
    ) -> tuple[list[str], list[str]]:
        """Cross-payload consistency. Returns (errors, warnings).

        Errors mean the facets contradict each other and a consumer would read a
        value that resolves to nothing. Warnings mean something is odd but every
        consumer still has a safe answer.
        """
        errors: list[str] = []
        warnings: list[str] = []

        for market, deals in data.available_deals.items():
            if market not in data.valid_markets:
                errors.append(f"deals returned for {market}, which is not a valid market")

            seen: set[str] = set()
            for deal in deals:
                if deal.deal_id in seen:
                    errors.append(f"duplicate deal ID {deal.deal_id} in {market}")
                seen.add(deal.deal_id)

                unsupported = set(deal.ad_lengths) - data.valid_durations
                if unsupported:
                    errors.append(
                        f"deal {deal.deal_id} offers durations {sorted(unsupported)} "
                        f"that the platform does not sell"
                    )

                if deal.provider not in data.tier_by_provider:
                    # Safe: the mapper already defaulted this deal to the most
                    # conservative tier. Worth saying, because a new provider
                    # arriving as "needs curation" is a commercial fact someone
                    # should confirm.
                    warnings.append(
                        f"provider {deal.provider!r} has no tier from the server - "
                        f"treated as {InventoryTierEnum.THIRD_PARTY_NEEDS_CURATION.value}"
                    )

        for market in data.market_targeting_configs:
            if market not in data.valid_markets:
                errors.append(f"targeting config for {market}, which is not a valid market")

        for market in data.product_categories:
            if market not in data.valid_markets:
                errors.append(f"product categories for {market}, which is not a valid market")

        for market in sorted(data.valid_markets):
            if market not in CURRENCY_BY_MARKET:
                errors.append(
                    f"market {market} has no currency mapping - step 1 cannot pick a currency"
                )

        for market, entries in data.rate_cards.items():
            off_card = {e.duration for e in entries} - data.valid_durations
            if off_card:
                warnings.append(f"{market} rate card prices durations {sorted(off_card)}")

        if not data.allowed_kpis <= CTV_KPIS:
            warnings.append(
                f"server allows KPIs outside CTV scope: {sorted(data.allowed_kpis - CTV_KPIS)}"
            )

        return errors, warnings

    def gate(self, data: GroundedRegistryData) -> list[str]:
        """Run every check. Raises on errors, returns the warnings to record."""
        errors = self.check_required_facets(data)
        integrity_errors, warnings = self.check_referential_integrity(data)
        errors += integrity_errors

        if errors:
            # The violations, not only how many. `RegistryValidationError` carries
            # them, but the handler in `sessions.chat` turns this into an opaque
            # "Agent error" 500, so the log line is the only place they survive -
            # and a count alone means the first question a diagnosis needs ("which
            # checks?") cannot be answered from the logs at all.
            logger.error(
                "registry.integrity_violation",
                extra=kv(count=len(errors), violations=errors[:5]),
            )
            raise RegistryValidationError(
                f"Reference data failed {len(errors)} integrity check(s); "
                f"refusing to ground against it.",
                violations=errors,
            )

        return warnings

    # --- versioning ---

    def diff(
        self, previous: GroundedRegistryData | None, current: GroundedRegistryData
    ) -> RegistryDiff:
        """What changed, as dotted paths. Empty when nothing did."""
        if previous is None:
            return RegistryDiff()

        before = _flatten(previous.model_dump(mode="json"))
        after = _flatten(current.model_dump(mode="json"))

        added = tuple(sorted(set(after) - set(before)))
        removed = tuple(sorted(set(before) - set(after)))

        changed, type_changed = [], []
        for path in sorted(set(before) & set(after)):
            if before[path] == after[path]:
                continue
            if type(before[path]) is not type(after[path]):
                type_changed.append(path)
            else:
                changed.append(path)

        return RegistryDiff(
            added=added,
            removed=removed,
            changed=tuple(changed),
            type_changed=tuple(type_changed),
        )

    def classify_compatibility(
        self, previous: GroundedRegistryData | None, diff: RegistryDiff
    ) -> Compatibility:
        """Whether the incoming shape is safe to swap in.

        A removed path or a changed type is breaking: something a consumer could
        already be reading has gone or changed meaning. New paths are additive.
        A changed *value* is additive too when it sits on a path declared as
        churn-prone - prices move daily, and an alarm that fires daily is not an
        alarm.
        """
        if previous is None:
            return "INITIAL"
        if diff.is_empty:
            return "IDENTICAL"
        if diff.removed or diff.type_changed:
            return "BREAKING"
        if any(not _is_value_churn(path) for path in diff.changed):
            return "BREAKING"
        return "ADDITIVE"

    def next_version(
        self,
        previous: RegistrySnapshotMeta | None,
        compatibility: Compatibility,
        content_hash: str,
    ) -> int:
        """Version counts content changes, not syncs.

        A sync that fetches identical data is not a new version - otherwise the
        number measures how often the TTL expired, which nobody wants to know.
        """
        if previous is None:
            return 1
        if compatibility == "IDENTICAL" or previous.content_hash == content_hash:
            return previous.version
        return previous.version + 1


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """Nested structure to {dotted.path: leaf}. Lists index by position."""
    flat: dict[str, Any] = {}

    if isinstance(value, dict):
        for key, item in value.items():
            flat.update(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            flat.update(_flatten(item, f"{prefix}[{index}]"))
    else:
        flat[prefix] = value

    return flat


def _is_value_churn(path: str) -> bool:
    leaf = path.rsplit(".", 1)[-1]
    return leaf in VALUE_CHURN_SEGMENTS


# --- flow-time validation ----------------------------------------------------


def _ok(message: str, **extra) -> ValidationResponse:
    return ValidationResponse(is_valid=True, message=message, **extra)


class StepwiseCTVValidator:
    """Grounds the trader's inputs for steps 1-7 against one snapshot.

    Synchronous everywhere except `validate_strategy_name`, and the asymmetry is
    the point: uniqueness is a question about mutable server state, so caching it
    would be wrong. Everything else is reference data, so caching it is right.
    """

    def __init__(self, snapshot: GroundedRegistrySnapshot, mcp=None):
        self.snapshot = snapshot
        self.data = snapshot.data
        self.mcp = mcp
        # Within one conversation a trader may propose the same name twice. Worth
        # remembering the answer; not worth persisting past the conversation.
        self._name_answers: dict[str, bool] = {}

    # --- step 1: basics ---

    async def validate_strategy_name(self, name: str) -> ValidationResponse:
        """Local rules first, then ask VOW whether the name is still free.

        Ordered that way so a 200-character name never costs a round trip. The
        suggestions on a collision are deliberately boring - a trader wants to
        accept one and move on, not to be surprised.
        """
        candidate = (name or "").strip()
        rules = self.data.strategy_name_rules

        if not candidate:
            return ValidationResponse(
                is_valid=False,
                code="strategy_name.empty",
                field="strategy_name",
                message="The strategy needs a name before I can continue.",
            )

        if len(candidate) > rules.max_length:
            return ValidationResponse(
                is_valid=False,
                code="strategy_name.too_long",
                field="strategy_name",
                message=(
                    f"That name is {len(candidate)} characters; VOW allows "
                    f"{rules.max_length}. Shorten it and I will check availability."
                ),
            )

        if rules.allowed_pattern and not re.match(rules.allowed_pattern, candidate):
            return ValidationResponse(
                is_valid=False,
                code="strategy_name.invalid_chars",
                field="strategy_name",
                message=(
                    "That name contains characters VOW will not accept. Letters, "
                    "numbers, spaces and - | . , ( ) & / are safe."
                ),
            )

        key = candidate if rules.case_sensitive else candidate.lower()
        if key in self._name_answers:
            is_unique = self._name_answers[key]
        elif self.mcp is None:
            # No client to ask, so say so rather than implying the name is free.
            return ValidationResponse(
                is_valid=False,
                code="strategy_name.unverified",
                severity="warning",
                field="strategy_name",
                message=(
                    "The name looks well-formed, but I cannot confirm it is unused "
                    "without reaching VOW."
                ),
            )
        else:
            from app.tools.mcp import VowTools

            response = await self.mcp.call_tool(VowTools.CHECK_STRATEGY_NAME, {"name": candidate})
            is_unique = bool(response.get("is_unique"))
            self._name_answers[key] = is_unique

        if not is_unique:
            return ValidationResponse(
                is_valid=False,
                code="strategy_name.duplicate",
                field="strategy_name",
                message=f"'{candidate}' is already taken in VOW. Shall I use one of these?",
                suggested_options=[
                    f"{candidate} v2",
                    f"{candidate} (2)",
                    f"{candidate} - draft",
                ],
            )

        return _ok(
            f"'{candidate}' is available.",
            code="strategy_name.ok",
            field="strategy_name",
            metadata={"normalized": candidate},
        )

    def validate_target_markets(self, markets: list[str]) -> ValidationResponse:
        """Grounds every market, reporting any it had to normalize.

        `UK` passes as a warning rather than an error: the trader is not wrong,
        the registry just stores `GB`, and saying so is a courtesy rather than a
        blocker.
        """
        if not markets:
            return ValidationResponse(
                is_valid=False,
                code="market.missing",
                field="target_markets",
                message="Which country should the campaign run in?",
                suggested_options=sorted(self.data.valid_markets),
            )

        normalized, unrecognised, renamed = [], [], {}
        for raw in markets:
            try:
                code = normalize_market(raw)
            except NormalizationError:
                unrecognised.append(raw)
                continue
            if code != str(raw).strip().upper():
                renamed[raw] = code
            normalized.append(code)

        ungrounded = [code for code in normalized if code not in self.data.valid_markets]

        if unrecognised or ungrounded:
            rejected = unrecognised + ungrounded
            return ValidationResponse(
                is_valid=False,
                code="market.unknown",
                field="target_markets",
                message=(
                    f"I cannot plan for {', '.join(str(r) for r in rejected)} - VOW does "
                    f"not sell CTV inventory there."
                ),
                suggested_options=sorted(self.data.valid_markets),
                metadata={"rejected": rejected, "accepted": normalized},
            )

        if renamed:
            spelled = ", ".join(f"{was} as {now}" for was, now in renamed.items())
            return ValidationResponse(
                is_valid=True,
                severity="warning",
                code="market.normalized",
                field="target_markets",
                message=f"Noted - I read {spelled}.",
                metadata={"normalized": normalized, "renamed": renamed},
            )

        return _ok(
            f"Targeting {', '.join(normalized)}.",
            code="market.ok",
            field="target_markets",
            metadata={"normalized": normalized},
        )

    def validate_currency(
        self, currency: str, markets: list[str] | None = None
    ) -> ValidationResponse:
        """Grounds the currency, and flags a mismatch with the market's own.

        A GBP budget on a US plan is legal but almost always a slip, so it passes
        as a warning rather than being silently accepted or wrongly rejected.
        """
        try:
            code = normalize_currency(currency)
        except NormalizationError:
            return ValidationResponse(
                is_valid=False,
                code="currency.unknown",
                field="primary_currency",
                message=f"VOW does not bill in {currency!r}.",
                suggested_options=sorted(self.data.valid_currencies),
            )

        if code not in self.data.valid_currencies:
            return ValidationResponse(
                is_valid=False,
                code="currency.unavailable",
                field="primary_currency",
                message=f"{code} is not available for this advertiser.",
                suggested_options=sorted(self.data.valid_currencies),
            )

        primary = markets[0] if markets else None
        expected = self.data.currency_for(primary) if primary else None
        if primary and expected and expected != code:
            return ValidationResponse(
                is_valid=True,
                severity="warning",
                code="currency.market_mismatch",
                field="primary_currency",
                message=(
                    f"Using {code} for a {primary} campaign - {expected} is the usual "
                    f"currency there. Say so if that is deliberate."
                ),
                metadata={"normalized": code, "market_default": expected},
            )

        return _ok(f"Billing in {code}.", code="currency.ok", metadata={"normalized": code})

    def validate_durations(
        self, durations: list[str], market: str | None = None
    ) -> ValidationResponse:
        """Grounds creative durations, and checks the market's rate card carries them.

        Two different questions, deliberately answered together: the platform may
        sell 10s while a given market's rate card does not price it, and a plan
        asking for one the market does not carry is a planning error worth
        catching now rather than at strategy creation.
        """
        if not durations:
            return ValidationResponse(
                is_valid=False,
                code="duration.missing",
                field="durations",
                message=f"Which creative durations - {duration_phrase()} seconds?",
                suggested_options=sorted(self.data.valid_durations, key=int),
            )

        normalized, unrecognised = [], []
        for raw in durations:
            try:
                normalized.append(normalize_duration(raw))
            except NormalizationError:
                unrecognised.append(raw)

        ungrounded = [d for d in normalized if d not in self.data.valid_durations]
        if unrecognised or ungrounded:
            return ValidationResponse(
                is_valid=False,
                code="duration.unknown",
                field="durations",
                message=(
                    f"CTV does not sell {', '.join(str(d) for d in unrecognised + ungrounded)}"
                    f"-second creatives."
                ),
                suggested_options=sorted(self.data.valid_durations, key=int),
            )

        if market:
            carried = self.data.carried_durations(normalize_market(market))
            off_card = [d for d in normalized if carried and d not in carried]
            if off_card:
                return ValidationResponse(
                    is_valid=True,
                    severity="warning",
                    code="duration.not_on_rate_card",
                    field="durations",
                    message=(
                        f"{', '.join(off_card)}-second is not on the {market} rate card, so "
                        f"I have no CPM for it there."
                    ),
                    suggested_options=sorted(carried, key=int),
                    metadata={"normalized": normalized, "off_rate_card": off_card},
                )

        return _ok(
            f"Creative durations: {', '.join(normalized)} seconds.",
            code="duration.ok",
            field="durations",
            metadata={"normalized": normalized},
        )

    def validate_goal_and_kpi(self, goal: str, kpi: str) -> ValidationResponse:
        """CTV is Awareness on reach or frequency. Everything else is future scope.

        The messages name the scope rather than the enum, because "invalid value"
        tells a trader nothing. Section 3 step 1 quotes the client: CTV is an
        awareness goal because it is hard to track further down the funnel.
        """
        try:
            goal_value = normalize_goal(goal)
        except NormalizationError:
            goal_value = None

        if goal_value not in self.data.allowed_goals:
            return ValidationResponse(
                is_valid=False,
                code="goal.out_of_scope",
                field="goal",
                message=(
                    f"CTV plans are Awareness only - it is hard to track anything further "
                    f"down the funnel, so {goal!r} is not something I can plan for here."
                ),
                suggested_options=sorted(self.data.allowed_goals),
            )

        try:
            kpi_value = normalize_kpi(kpi)
        except NormalizationError:
            kpi_value = None

        if kpi_value not in self.data.allowed_kpis or kpi_value not in CTV_KPIS:
            return ValidationResponse(
                is_valid=False,
                code="kpi.out_of_scope",
                field="kpi",
                message=(
                    f"For CTV I can optimise for reach or frequency. {kpi!r} needs "
                    f"down-funnel tracking that CTV does not provide."
                ),
                suggested_options=sorted(CTV_KPIS),
            )

        return _ok(
            f"Goal {goal_value}, measured on {kpi_value}.",
            code="goal_kpi.ok",
            metadata={"normalized": {"goal": goal_value, "kpi": kpi_value}},
        )

    def validate_flight_dates(
        self, flight_dates: dict | None, today: date | None = None
    ) -> ValidationResponse:
        """Grounded-object form of `check_flight_dates`. See that function."""
        return check_flight_dates(flight_dates, today)

    def validate_product_categories(
        self, market: str, category_ids: list[int]
    ) -> ValidationResponse:
        """Grounds contextual categories against the market's own list.

        Degrades rather than blocking when the categories source was unavailable:
        an optional facet going missing must not stop a plan.
        """
        code = normalize_market(market)
        available = self.data.product_categories.get(code, ())

        if not available:
            return ValidationResponse(
                is_valid=True,
                severity="warning",
                code="product_categories.unavailable",
                field="product_categories",
                message=f"I have no product-category list for {code}, so I cannot check these.",
                metadata={"market": code},
            )

        known = {c.id for c in available}
        unknown = [cid for cid in category_ids if cid not in known]
        if unknown:
            return ValidationResponse(
                is_valid=False,
                code="product_categories.unknown",
                field="product_categories",
                message=f"Product categories {unknown} are not available in {code}.",
                suggested_options=[c.name for c in available],
                metadata={"available": [{"id": c.id, "name": c.name} for c in available]},
            )

        return _ok(
            f"{len(category_ids)} product category(ies) confirmed for {code}.",
            code="product_categories.ok",
            field="product_categories",
        )

    # --- step 2: inventory and the tier fork ---

    def validate_deal_selection(
        self,
        market: str,
        deal_ids: list[str],
        curation: dict | None = None,
    ) -> ValidationResponse:
        """The flow's primary fork - section 3 step 2.

        Classifies the selection into the three tiers and reports what each
        unlocks. Selecting needs-curation inventory (Disney+) without the details
        VOW needs to curate it later is not an error in the plan, it is a missing
        input, so it comes back as a request for those five fields.

        **Not called by any node yet, on purpose.** There is no trader-facing
        deal-selection step, so every plan carries all matching inventory, which
        in most markets includes Disney+ - and this would then return
        `curation_required` on every campaign. Nothing could answer it: the state
        has no slot for the details and no node collects them, so the
        conversation would stop at a question with no way to reply.

        Two things must land first, both already named in the contract rather
        than needing new vocabulary:

          * `curation_requirements: list[dict]` on `PlanningAgentState`
            (`VOW_Strategy_Schema_v2.md` section 5, line 749)
          * a `capture_curation_requirements` node (section 6, line 799)

        With those in place this becomes the gate in front of it. Until then it
        is exercised only by its unit tests.
        """
        code = normalize_market(market)
        available = self.data.deals(code)

        if not deal_ids:
            return ValidationResponse(
                is_valid=False,
                code="deal.missing",
                field="selected_deals",
                message=f"Which CTV inventory should I plan against in {code}?",
                suggested_options=[d.deal_id for d in available],
            )

        by_id = {d.deal_id: d for d in available}
        unknown = [d for d in deal_ids if d not in by_id]
        if unknown:
            return ValidationResponse(
                is_valid=False,
                code="deal.unknown",
                field="selected_deals",
                message=(
                    f"I have no deal {', '.join(unknown)} in {code}. I will not invent one - "
                    f"here is what is actually available."
                ),
                suggested_options=[d.deal_id for d in available],
                metadata={
                    "available": [
                        {"deal_id": d.deal_id, "provider": d.provider, "cpm": money_str(d.cpm)}
                        for d in available
                    ]
                },
            )

        selected = [by_id[d] for d in deal_ids]
        by_tier: dict[str, list[str]] = {tier.value: [] for tier in InventoryTierEnum}
        for deal in selected:
            label = f"{deal.provider}{f' | {deal.genre}' if deal.genre else ''}"
            by_tier[deal.inventory_tier.value].append(label)

        dominant = dominant_tier(selected)
        forecastable = any(d.supports_reach_forecast for d in selected)
        needs_curation = [
            d for d in selected if d.inventory_tier is InventoryTierEnum.THIRD_PARTY_NEEDS_CURATION
        ]

        metadata = {
            "inventory_summary": {k: v for k, v in by_tier.items() if v},
            "dominant_tier": dominant.value if dominant else None,
            "forecastable": forecastable,
            "curation_required": bool(needs_curation),
            "tier_labels": {d.deal_id: TIER_LABELS[d.inventory_tier] for d in selected},
        }

        if needs_curation and not curation:
            providers = sorted({d.provider for d in needs_curation})
            return ValidationResponse(
                is_valid=False,
                code="deal.curation_required",
                field="curation_details",
                message=(
                    f"{', '.join(providers)} inventory is not selectable yet - VOW curates "
                    f"the deal after the IO is signed. I need a few details to pass on."
                ),
                suggested_options=sorted(self.data.curation_genres),
                metadata={
                    **metadata,
                    "curation_fields": list(CURATION_FIELDS),
                    "available_genres": sorted(self.data.curation_genres),
                },
            )

        return _ok(
            f"{len(selected)} deal(s) selected in {code}.",
            code="deal.ok",
            field="selected_deals",
            metadata=metadata,
        )

    def validate_curation_requirements(self, curation: dict) -> ValidationResponse:
        """The other arm of the fork: what VOW needs to curate a deal later.

        Section 3 step 2 lists targeting preferences as optional; the rest are
        required, because without them there is nothing for VOW to build.
        """
        required = [f for f in CURATION_FIELDS if f != "targeting_preferences"]
        missing = [field for field in required if not curation.get(field)]

        if missing:
            return ValidationResponse(
                is_valid=False,
                code="curation.incomplete",
                field="curation_details",
                message=(f"For VOW to curate this inventory I still need: {', '.join(missing)}."),
                metadata={
                    "missing": missing,
                    "available_genres": sorted(self.data.curation_genres),
                },
            )

        genres = [str(g) for g in (curation.get("genres") or [])]
        unknown = [
            g for g in genres if self.data.curation_genres and g not in self.data.curation_genres
        ]
        if unknown:
            return ValidationResponse(
                is_valid=False,
                code="curation.unknown_genre",
                field="curation_details",
                message=f"I have no inventory tagged {', '.join(unknown)}.",
                suggested_options=sorted(self.data.curation_genres),
            )

        return _ok("Curation details captured.", code="curation.ok", field="curation_details")

    def genre_upsell_candidates(self, market: str, provider: str) -> list[dict]:
        """Genre deals priced above the same provider's run-of-service.

        Section 3 step 2, from the client: "based on the brief we can suggest
        whether a specific available genre would be a better match at a slightly
        higher CPM". Only meaningful within one provider, where the CPM difference
        buys a better contextual match rather than different inventory.

        Returns facts and no judgement - whether the brief implies the genre is
        the agent's call, not the registry's.
        """
        deals = [d for d in self.data.deals(normalize_market(market)) if d.provider == provider]
        base = next((d for d in deals if not d.genre), None)
        if base is None:
            return []

        return [
            {
                "genre": deal.genre,
                "deal_id": deal.deal_id,
                "cpm": money_str(deal.cpm),
                "base_cpm": money_str(base.cpm),
                "uplift": money_str(deal.cpm - base.cpm),
            }
            for deal in deals
            if deal.genre and deal.cpm > base.cpm
        ]

    # --- step 3: budget split ---

    def validate_split_method(self, method: str) -> ValidationResponse:
        """Grounds the split method, and states what it does to impressions.

        Section 3 step 3 requires the agent to say which it chose and why, so the
        consequence travels with the validation rather than being re-derived in a
        node.
        """
        try:
            value = normalize_split_method(method)
        except NormalizationError:
            return ValidationResponse(
                is_valid=False,
                code="split_method.unknown",
                field="budget_split",
                message=f"I do not know how to split a budget {method!r}.",
                suggested_options=sorted(self.data.supported_split_methods),
            )

        if value not in self.data.supported_split_methods:
            return ValidationResponse(
                is_valid=False,
                code="split_method.unsupported",
                field="budget_split",
                message=f"{value} is not a split method VOW supports.",
                suggested_options=sorted(self.data.supported_split_methods),
            )

        consequence = {
            "EVEN_BY_BUDGET": "same spend per line, so uneven impressions - a higher CPM buys fewer",
            "EVEN_BY_IMPRESSIONS": "same impressions per line, so uneven spend - a higher CPM costs more",
            "CUSTOM": "allocations exactly as given",
        }[value]

        return _ok(
            f"Splitting {value}: {consequence}.",
            code="split_method.ok",
            field="budget_split",
            metadata={"normalized": value, "consequence": consequence},
        )

    # --- step 4: audiences ---

    def validate_audience_choice(self, profile: str) -> ValidationResponse:
        try:
            value = normalize_profile(profile)
        except NormalizationError:
            return ValidationResponse(
                is_valid=False,
                code="audience.unknown_profile",
                field="chosen_audience",
                message=f"{profile!r} is not one of the three audience options.",
                suggested_options=sorted(self.data.audience_profiles),
            )

        if value not in self.data.audience_profiles:
            return ValidationResponse(
                is_valid=False,
                code="audience.profile_unavailable",
                field="chosen_audience",
                message=f"VOW did not suggest a {value.lower()} audience for this brief.",
                suggested_options=sorted(self.data.audience_profiles),
            )

        return _ok(
            f"{value.title()} audience selected.",
            code="audience.ok",
            field="chosen_audience",
            metadata={"normalized": value},
        )

    def validate_matching_mode(self, mode: str) -> ValidationResponse:
        try:
            value = normalize_matching_mode(mode)
        except NormalizationError:
            return ValidationResponse(
                is_valid=False,
                code="matching_mode.unknown",
                field="matching_mode",
                message=f"Audience matching is Similar or Exact, not {mode!r}.",
                suggested_options=sorted(self.data.matching_modes),
            )

        return _ok(
            f"{value} audience matching.",
            code="matching_mode.ok",
            field="matching_mode",
            metadata={"normalized": value},
        )

    def effective_cpm_options(self, market: str, deal_ids: list[str] | None = None) -> list[dict]:
        """All three audience profiles priced against the selected inventory.

        Section 3 step 4 wants the effective CPM shown per option, because the
        deal price alone understates what precision costs. Priced off the
        cheapest Amazon deal - Amazon audiences apply to Amazon-owned inventory
        only, so a plan with none gets `None` rather than a number that would
        imply the fee buys something.
        """
        deals = self.data.deals(normalize_market(market))
        if deal_ids:
            deals = tuple(d for d in deals if d.deal_id in set(deal_ids))

        base = cheapest_amazon_cpm(deals)

        options = []
        for profile in ("NARROW", "BALANCED", "WIDE"):
            item = self.data.audience_profiles.get(profile)
            if item is None:
                continue
            options.append(
                {
                    "audience_set_id": item.audience_set_id,
                    "name": item.name,
                    "profile": profile,
                    "vcpm_fee": money_str(item.vcpm_fee),
                    "segment_count": item.segment_count,
                    "estimated_size": item.estimated_size,
                    "cpm_basis": money_str(base) if base is not None else None,
                    "effective_cpm": (
                        money_str(calculate_effective_cpm(base, item.vcpm_fee))
                        if base is not None
                        else None
                    ),
                }
            )

        return options

    # --- step 5: targeting ---

    def get_targeting_options_for_market(self, market: str) -> ValidationResponse:
        """The market's targeting surface, or an honest "not available".

        Reports unavailable rather than raising when the config or the source did
        not load: targeting is optional in section 3 step 5, so its absence must
        not stop a plan.
        """
        code = normalize_market(market)
        config = self.data.targeting(code)

        if config is None or not config.options:
            return ValidationResponse(
                is_valid=True,
                severity="warning",
                code="targeting.unavailable",
                field="targeting",
                message=f"I have no targeting options for {code}, so I will leave targeting open.",
                metadata={"market": code, "config": None},
            )

        return _ok(
            f"{len(config.options)} targeting type(s) available in {code}.",
            code="targeting.ok",
            field="targeting",
            metadata={"market": code, "config": config.model_dump(mode="json")},
        )

    def validate_targeting(
        self, market: str, selections: dict[str, list[str]]
    ) -> ValidationResponse:
        """Grounds every selected key and value, and enforces cardinality."""
        code = normalize_market(market)
        config = self.data.targeting(code)

        if config is None or not config.options:
            return ValidationResponse(
                is_valid=True,
                severity="warning",
                code="targeting.unavailable",
                field="targeting",
                message=f"I cannot check targeting for {code} - I have no options list for it.",
            )

        unknown_keys = sorted(set(selections) - set(config.options))
        if unknown_keys:
            return ValidationResponse(
                is_valid=False,
                code="targeting.unknown_type",
                field="targeting",
                message=f"VOW has no targeting type called {', '.join(unknown_keys)}.",
                suggested_options=sorted(config.options),
            )

        problems: list[str] = []
        for key, values in selections.items():
            option = config.options[key]
            unknown_values = [v for v in values if v not in option.value_ids()]
            if unknown_values:
                problems.append(f"{option.label}: {', '.join(unknown_values)} is not an option")
            if option.cardinality == "single" and len(values) > 1:
                problems.append(f"{option.label} takes one value, not {len(values)}")

        if problems:
            return ValidationResponse(
                is_valid=False,
                code="targeting.invalid_selection",
                field="targeting",
                message="; ".join(problems),
                metadata={
                    "available": {
                        key: sorted(option.value_ids()) for key, option in config.options.items()
                    }
                },
            )

        return _ok(
            f"Targeting confirmed for {code}.",
            code="targeting.ok",
            field="targeting",
            metadata={"selections": selections},
        )

    # --- step 6: forecast ---

    def is_forecastable(self, market: str, deal_ids: list[str] | None = None) -> bool:
        """Whether reach can be forecast at all - Amazon-owned inventory only.

        Section 3 step 6's honesty rule, as one registry fact rather than a tier
        comparison scattered across nodes.
        """
        deals = self.data.deals(normalize_market(market))
        if deal_ids:
            deals = tuple(d for d in deals if d.deal_id in set(deal_ids))
        return any(d.supports_reach_forecast for d in deals)

    def validate_forecast_shape(self, payload: dict) -> ValidationResponse:
        """Grounded-object form of `check_forecast_shape`. See that function."""
        return check_forecast_shape(payload)

    def validate_plan_ready_for_approval(self, state: dict) -> ValidationResponse:
        """Every reason the plan is not ready, in one answer.

        `ask_for_missing` deliberately asks for everything at once rather than
        drip-feeding, so this returns the whole list. Approval is the point where
        budget is locked (section 3 step 7), which is the wrong moment to
        discover a gap.
        """
        violations: list[str] = []

        checks = [
            ("a strategy name", state.get("strategy_name")),
            ("the flight dates", state.get("flight_dates")),
            ("at least one market", state.get("markets")),
            ("the creative durations", state.get("durations")),
            ("a budget", state.get("market_budgets")),
            ("selected inventory", state.get("selected_deals")),
            ("a chosen audience", state.get("chosen_audience")),
            ("a forecast", state.get("forecast")),
        ]
        violations += [f"I still need {label}" for label, value in checks if not value]

        markets = state.get("markets") or []
        if markets:
            market_check = self.validate_target_markets(list(markets))
            if market_check.blocks:
                violations.append(market_check.message)

        goal, kpi = state.get("goal"), state.get("kpi")
        if goal and kpi:
            goal_check = self.validate_goal_and_kpi(goal, kpi)
            if goal_check.blocks:
                violations.append(goal_check.message)

        forecast = state.get("forecast")
        if forecast:
            shape = self.validate_forecast_shape(forecast)
            if shape.blocks:
                violations.append(shape.message)

        # `validation_errors` holds serialized `ValidationResponse`s (see
        # `agent/gates.record`), warnings among them. Only blockers belong here: a
        # warning is something the agent already said and the trader chose to live
        # with, so folding it in would make an acknowledged note refuse approval.
        violations += [
            entry["message"]
            for entry in (state.get("validation_errors") or [])
            if isinstance(entry, dict)
            and not entry.get("is_valid")
            and entry.get("severity") == "error"
            and entry.get("message")
        ]

        if violations:
            return ValidationResponse(
                is_valid=False,
                code="plan.not_ready",
                field="approval_status",
                message="The plan is not ready to approve yet: " + "; ".join(violations),
                metadata={"violations": violations},
            )

        return _ok(
            "The plan is complete and ready for approval.",
            code="plan.ready",
            field="approval_status",
        )


def assert_grounded(response: ValidationResponse) -> None:
    """Raise `GroundingError` when proceeding would be unacceptable.

    The only place in the codebase that raises it. Call this where an ungrounded
    value would leave the process - before creating a strategy, or anywhere a
    deal ID or audience set ID is about to be sent to VOW. Everywhere else, take
    the `ValidationResponse` and let the agent ask.
    """
    if response.blocks:
        raise GroundingError(f"{response.field or 'value'} is not grounded: {response.message}")
