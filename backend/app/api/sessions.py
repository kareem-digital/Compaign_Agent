import logging
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.agent.checkpointer import create_checkpointer
from app.agent.graph import build_graph
from app.agent.voice import render_turn
from app.api.presentation import Block, build_blocks
from app.api.validation_details import ValidationDetails, build_validation_details
from app.config import get_settings
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.core.context import bind
from app.core.exceptions import (
    AdvertiserContextMissingError,
    KillSwitchEngagedError,
    MCPError,
    PolicyDeniedError,
    RegistrySyncError,
    RegistryValidationError,
)
from app.core.logging import kv
from app.tools.mcp import create_mcp_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

_checkpointer = None
# One compiled graph per advertiser, because the MCP client is bound into the
# nodes and is advertiser-scoped. Fine at this scale; bound it (or move the
# client into per-invocation config) before this serves many tenants.
_graphs: dict[str, object] = {}


def _resolve_advertiser(header_value: str | None) -> str:
    """Advertiser context for this call.

    Fails closed everywhere except local dev, where a configured fallback keeps
    the chat endpoint usable before the UI sends the header. Never guesses in
    staging or production - a call attributed to the wrong tenant is worse than
    a rejected one.
    """
    if header_value:
        return header_value

    settings = get_settings()
    if settings.environment == "local" and settings.dev_advertiser_id:
        logger.warning(
            "No Vowmade-Advertiser-Id header; using dev fallback %s. Local only.",
            settings.dev_advertiser_id,
        )
        return settings.dev_advertiser_id

    raise HTTPException(
        status_code=400,
        detail="Vowmade-Advertiser-Id header is required.",
    )


async def _get_graph(advertiser_id: str):
    global _checkpointer

    if _checkpointer is None:
        _checkpointer = await create_checkpointer()

    if advertiser_id not in _graphs:
        _graphs[advertiser_id] = build_graph(
            checkpointer=_checkpointer,
            mcp=create_mcp_client(advertiser_id),
        )
        logger.info("Planning graph initialised for advertiser %s", advertiser_id)

    return _graphs[advertiser_id]


class WireContentBlock(BaseModel):
    """A single block in the request content array sent by the frontend."""
    type: str
    text: str | None = None
    elicitation_id: str | None = None
    selected_option_ids: list[str] | None = None
    custom_text: str | None = None


class WireMessage(BaseModel):
    """The structured message envelope the UI team's wire.ts expects."""
    id: str
    role: str = "assistant"
    content: list[Any] = Field(default_factory=list)


class ChatRequest(BaseModel):
    # Plain-text fallback — used when content[] is absent or has no text block.
    message: str | None = Field(None, max_length=2000)
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Send the same ID to continue a conversation; omit to start new.",
    )
    # Idempotency key the frontend mints per turn (see wire.ts WireChatRequest).
    client_message_id: str | None = Field(None)
    # Structured blocks from the frontend (text + options_response blocks).
    content: list[WireContentBlock] = Field(default_factory=list)

    def plain_text(self) -> str:
        """Extract the human-readable text the agent should process."""
        parts: list[str] = []
        for block in self.content:
            if block.type == "text" and block.text:
                parts.append(block.text)
            elif block.type == "options_response":
                if block.custom_text:
                    parts.append(block.custom_text)
                elif block.selected_option_ids:
                    cleaned: list[str] = []
                    for opt_id in block.selected_option_ids:
                        val = opt_id.replace("opt_", "")
                        if val in ("10", "15", "20", "30"):
                            cleaned.append(f"{val} seconds")
                        elif val.lower() in ("uk", "gb"):
                            cleaned.append("United Kingdom")
                        elif val.lower() in ("us", "usa"):
                            cleaned.append("United States")
                        elif val.lower() == "fr":
                            cleaned.append("France")
                        elif val.lower() == "de":
                            cleaned.append("Germany")
                        elif val.lower() in ("narrow", "balanced", "wide"):
                            cleaned.append(f"{val} audience")
                        else:
                            cleaned.append(val.replace("_", " "))
                    parts.append(", ".join(cleaned))
        if parts:
            return " ".join(parts)
        # Fall back to the legacy `message` field.
        return self.message or ""


class ChatResponse(BaseModel):
    session_id: str
    # Plain-text mirror — kept so nothing that reads only `reply` breaks.
    reply: str
    stage: str | None = Field(
        None, description="Stage the plan reached on this turn, e.g. 'forecast'."
    )
    # Structured message envelope — what wire.ts WireChatResponse.message maps to.
    # The UI reads message.content[] for elicitation blocks; reply is the fallback.
    message: WireMessage | None = Field(None)
    # Grounding detail for the validation panel.
    validation: ValidationDetails
    # Legacy presentation blocks — kept for backward compatibility.
    blocks: list[Block] = Field(
        default_factory=list,
        description=(
            "The reply broken into renderable pieces. Each says what it is, how "
            "it should appear, and carries the data behind it. `reply` remains "
            "the plain-text equivalent."
        ),
    )
    # Plan field values formatted for the StrategyPanel — what wire.ts
    # WireChatResponse.plan_state maps to. Keys are field names, values are
    # human-readable strings already formatted by the backend.
    plan_state: dict[str, str] = Field(default_factory=dict)
    # Elicitations whose status changed this turn (answered / superseded).
    resolved_elicitations: list[Any] = Field(default_factory=list)
    resolved_blocks: list[Any] = Field(default_factory=list)
    plan_version: int = 0


class SessionState(BaseModel):
    session_id: str
    message_count: int
    stage: str | None = None
    next_node: list[str] | None = None
    # Here as well as on `ChatResponse`, so reopening a session restores the panel
    # instead of leaving it blank until the trader says something else.
    validation: ValidationDetails
    plan_state: dict[str, str] = Field(default_factory=dict)


def _content(message) -> str:
    return str(
        getattr(message, "content", None)
        or (message.get("content", "") if isinstance(message, dict) else "")
    )


def _is_assistant(message) -> bool:
    if getattr(message, "type", None) == "ai":
        return True
    return isinstance(message, dict) and message.get("role") == "assistant"


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    vowmade_advertiser_id: Annotated[
        str | None,
        Header(alias="Vowmade-Advertiser-Id"),
    ] = None,
):
    advertiser_id = _resolve_advertiser(vowmade_advertiser_id)
    bind(session_id=request.session_id, advertiser_id=advertiser_id)

    graph = await _get_graph(advertiser_id)
    thread_config = {
        "configurable": {
            "thread_id": f"{current_user.subject}:{advertiser_id}:{request.session_id}",
        }
    }

    # Message count before this turn, so we can return only what this turn said
    # rather than the whole transcript.
    prior = await graph.aget_state(thread_config)
    prior_count = len(prior.values.get("messages", [])) if prior and prior.values else 0

    started = time.monotonic()
    user_text = request.plain_text()
    logger.info(
        "turn.start",
        extra=kv(turn=(prior_count // 5) + 1, message_chars=len(user_text)),
    )
    # The brief itself is client-commercial data, so content stays at DEBUG.
    logger.debug("turn.message", extra=kv(text=user_text))

    try:
        result = await graph.ainvoke(
            {
                "messages": [{"role": "user", "content": user_text}],
                "advertiser_id": advertiser_id,
                "session_id": request.session_id,
            },
            config=thread_config,
        )
    except AdvertiserContextMissingError as exc:
        logger.error("turn.failed", extra=kv(reason="no_advertiser_context"))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KillSwitchEngagedError as exc:
        # 503, not 403. This is temporary and deliberate, so the caller should
        # understand it may work later - the opposite of a policy refusal.
        logger.critical("turn.halted", extra=kv(reason="kill_switch"))
        raise HTTPException(status_code=503, detail="The agent is temporarily halted.") from exc
    except PolicyDeniedError as exc:
        # A refusal is the system working, not failing - hence a distinct event
        # name and WARNING rather than ERROR. Counting `turn.refused` by rule
        # tells you which guardrail actually fires, which is what the gate will
        # ask.
        #
        # The client is told only that the action is not permitted. Tool names,
        # rule names and the engine's reasoning are internal and stay in the
        # log. The response still carries X-Request-ID, so a support question
        # can be traced to the exact decision.
        logger.warning(
            "turn.refused",
            extra=kv(
                reason="policy_denied",
                tool=exc.tool,
                rule=exc.rule or "default",
                detail=str(exc),
            ),
        )
        raise HTTPException(status_code=403, detail="This action is not permitted.") from exc
    except MCPError as exc:
        logger.exception(
            "turn.failed", extra=kv(reason="mcp_error", tool=getattr(exc, "tool", None))
        )
        raise HTTPException(status_code=502, detail=f"VOW is unavailable: {exc}") from exc
    except RegistryValidationError as exc:
        # Before RegistrySyncError, which it subclasses - reversing these two
        # would swallow the validation case and lose the violation list.
        #
        # Distinct from a sync failure: VOW answered, and what it said did not
        # pass the integrity checks. The violation list is the whole reason that
        # error carries one, so it goes to the log.
        logger.exception(
            "turn.failed",
            extra=kv(
                reason="registry_validation",
                violations=exc.violations[:20],
                violation_count=len(exc.violations),
            ),
        )
        raise HTTPException(
            status_code=503,
            detail="Reference data from VOW did not pass validation, so planning is paused.",
        ) from exc
    except RegistrySyncError as exc:
        # Reference data could not be built at all. Reporting this as a generic
        # "Agent error" is what used to send people looking at the graph when the
        # problem was upstream.
        logger.exception("turn.failed", extra=kv(reason="registry_sync"))
        raise HTTPException(
            status_code=503,
            detail="Reference data from VOW could not be loaded, so planning is paused.",
        ) from exc
    except Exception:
        logger.exception("turn.failed", extra=kv(reason="graph_error"))
        raise HTTPException(status_code=500, detail="Agent error") from None

    new_messages = result.get("messages", [])[prior_count:]
    replies = [_content(m) for m in new_messages if _is_assistant(m)]

    elapsed_ms = round((time.monotonic() - started) * 1000)
    awaiting = result.get("awaiting") or []
    logger.info(
        "turn.end",
        extra=kv(
            stage=result.get("current_stage"),
            duration_ms=elapsed_ms,
            nodes_run=len(replies),
            blocked=bool(awaiting),
            awaiting_count=len(awaiting),
        ),
    )

    # The measurement G1 depends on: how many turns a complete plan took.
    # Reconstructing this after the fact is impossible, so it is recorded here.
    if result.get("forecast") and not awaiting:
        logger.info(
            "plan.completed",
            extra=kv(
                turns=(len(result.get("messages", [])) // 5),
                forecast_available=result["forecast"].get("is_available"),
                inventory_tier=result.get("inventory_tier"),
            ),
        )

    if not replies:
        logger.error("turn.failed", extra=kv(reason="no_reply_produced"))
        raise HTTPException(status_code=500, detail="Agent produced no response")

    # The graph runs several nodes per turn and each one speaks. Re-voiced into one
    # reply so the transport contract stays a single string - and so the trader
    # reads a turn rather than three stacked blocks. `render_turn` returns the
    # plain join whenever it cannot do better, so this cannot fail the request.
    #
    # The blocks themselves stay in `state["messages"]` untouched. That is what
    # `gates.say` fingerprints and what the audit replays; see `agent.voice`.
    reply = await render_turn(
        replies,
        trader_message=user_text,
        stage=result.get("current_stage"),
        # From state rather than from the prose: the providers worth protecting in
        # a rewrite are the ones the plan actually holds.
        providers=tuple(
            dict.fromkeys(
                deal["provider"]
                for deal in result.get("selected_deals") or []
                if deal.get("provider")
            )
        ),
    )

    # Build the plan_state dict: field name -> human-readable string.
    # This is what the StrategyPanel reads via WireChatResponse.plan_state.
    plan_state = _build_plan_state(result)

    # Build the structured message envelope the UI team's wire.ts expects.
    # content[] mirrors what blocks[] carries but in the elicitation-aware format.
    presentation_blocks = build_blocks(result)
    wire_content: list[Any] = []
    if reply:
        wire_content.append({"type": "text", "text": reply})

    current_stage = result.get("current_stage")
    # Only emit interactive elicitation options if the plan is still awaiting an answer
    if current_stage != "delivered":
        # Find the single active interactive block to emit
        interactive_blocks = [
            b for b in presentation_blocks
            if b.interaction in ("select_one", "select_many", "confirm")
        ]
        # Prefer the primary block, or the last interactive block
        target_block = next((b for b in interactive_blocks if b.primary), None) or (
            interactive_blocks[-1] if interactive_blocks else None
        )

        if target_block is not None:
            raw_options = target_block.data.get("options") or []
            if not raw_options and target_block.data.get("rows"):
                raw_options = [
                    {"value": row.get("value", row.get("provider", "")),
                     "label": row.get("provider", row.get("label", "")),
                     "description": (
                         f'CPM: {row.get("cpm", "")}'
                         + (f' · {row.get("lengths", "")}' if row.get("lengths") else "")
                         + (f' · {row.get("tier", "")}' if row.get("tier") else "")
                     ),
                     "badge": "Amazon-owned" if "Amazon" in (row.get("tier") or "") else None}
                    for row in target_block.data["rows"]
                ]
            wire_content.append({
                "type": "options",
                "id": f"elc_{target_block.field or target_block.layout}.{abs(hash(reply)) % 0xFFFFFFFF:08x}",
                "prompt": target_block.text,
                "select": "single" if target_block.interaction == "select_one" else "multi",
                "allow_custom": True,
                "custom_placeholder": "Answer in your own words…",
                "allow_skip": False,
                "allow_reopen": False,
                "status": "pending",
                "options": [
                    {
                        "id": f'opt_{str(o.get("value", o.get("label", ""))).lower().replace(" ", "_")}',
                        "label": str(o.get("label", o.get("value", ""))),
                        "description": o.get("description") or None,
                        "badge": o.get("badge") or None,
                    }
                    for o in raw_options
                ],
                "answer": None,
            })

    wire_msg = WireMessage(
        id=f"msg_{uuid.uuid4()}",
        role="assistant",
        content=wire_content,
    )

    # Build resolved_elicitations for any answered questions this turn
    from datetime import datetime, timezone
    resolved_elicitations: list[Any] = []
    for block in request.content:
        if block.type == "options_response" and block.elicitation_id:
            resolved_elicitations.append({
                "type": "options",
                "id": block.elicitation_id,
                "prompt": "",
                "select": "multi" if len(block.selected_option_ids or []) > 1 else "single",
                "options": [],
                "status": "answered",
                "answer": {
                    "selected_option_ids": block.selected_option_ids or [],
                    "custom_text": block.custom_text,
                    "answered_at": datetime.now(timezone.utc).isoformat(),
                },
            })

    return ChatResponse(
        session_id=request.session_id,
        reply=reply,
        stage=result.get("current_stage"),
        message=wire_msg,
        validation=build_validation_details(result),
        blocks=presentation_blocks,
        plan_state=plan_state,
        resolved_elicitations=resolved_elicitations,
        resolved_blocks=resolved_elicitations,
        plan_version=int(result.get("plan_version", 0) or 0),
    )


@router.get("/{session_id}", response_model=SessionState)
async def get_session(
    session_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    vowmade_advertiser_id: Annotated[
        str | None,
        Header(alias="Vowmade-Advertiser-Id"),
    ] = None,
):
    advertiser_id = _resolve_advertiser(vowmade_advertiser_id)
    bind(session_id=session_id, advertiser_id=advertiser_id)
    graph = await _get_graph(advertiser_id)
    thread_config = {
        "configurable": {
            "thread_id": f"{current_user.subject}:{advertiser_id}:{session_id}",
        }
    }

    # A checkpointer failure is not a missing session. Reporting one as the other
    # is how a real outage gets triaged as "the trader mistyped an ID" - so the
    # read is logged before it is translated, and only an empty result is a 404.
    try:
        state = await graph.aget_state(thread_config)
    except Exception as exc:
        logger.exception(
            "session.read_failed",
            extra=kv(session_id=session_id, reason=type(exc).__name__),
        )
        raise HTTPException(status_code=503, detail="Session store is unavailable.") from exc

    if not state or not state.values:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return SessionState(
        session_id=session_id,
        message_count=len(state.values.get("messages", [])),
        stage=state.values.get("current_stage"),
        next_node=list(state.next) if state.next else None,
        validation=build_validation_details(state.values),
        plan_state=_build_plan_state(state.values),
    )


def _build_plan_state(state: dict) -> dict[str, str]:
    """Map graph state fields -> human-readable strings for the StrategyPanel.

    Keys match the LABELS dict in http-agent-client.ts so the frontend can
    render them directly without any mapping logic of its own.
    """
    out: dict[str, str] = {}

    if state.get("strategy_name"):
        out["strategy_name"] = str(state["strategy_name"])
    if state.get("advertiser_id"):
        out["brand"] = f"Advertiser ({state['advertiser_id']})"

    # Markets
    markets = state.get("markets") or []
    if markets:
        out["markets"] = ", ".join(markets)

    # Flight dates
    flight_dates = state.get("flight_dates")
    if flight_dates:
        out["flight_dates"] = f'{flight_dates.get("lower", "")} to {flight_dates.get("upper", "")}'
    elif state.get("flight_start"):
        start = state.get("flight_start", "")
        end = state.get("flight_end", "")
        out["flight_dates"] = f"{start} to {end}" if end else start

    # Creative durations
    durations = state.get("durations") or []
    if durations:
        out["durations"] = ", ".join(f"{d}s" for d in durations)

    # Budget
    market_budgets = state.get("market_budgets") or []
    currency = state.get("primary_currency") or ""
    if market_budgets:
        budget = market_budgets[0].get("budget", "")
        out["market_budgets"] = f"{budget} {currency}".strip()
    elif state.get("budget_amount"):
        out["market_budgets"] = f'{state["budget_amount"]} {currency}'.strip()

    # Goal & KPI
    if state.get("goal"):
        out["goal"] = str(state["goal"]).capitalize()
    if state.get("kpi"):
        out["kpi"] = str(state["kpi"]).capitalize()

    # Inventory
    deals = state.get("selected_deals") or []
    if deals:
        providers = list(dict.fromkeys(d.get("provider", "") for d in deals if d.get("provider")))
        out["inventory"] = ", ".join(providers)
    if state.get("inventory_tier"):
        out["inventory_tier"] = str(state["inventory_tier"]).replace("_", " ").title()

    # Audience
    chosen = state.get("chosen_audience")
    if chosen and chosen.get("profile"):
        out["audience"] = str(chosen["profile"]).capitalize()

    # Targeting
    geo_targets = state.get("geo_targets") or []
    if geo_targets:
        out["targeting"] = ", ".join(t.get("name", t.get("id", "")) for t in geo_targets)
    elif state.get("targeting_confirmed"):
        out["targeting"] = "Market baseline (default)"

    # Demographics
    demographics = state.get("demographics")
    if demographics and isinstance(demographics, dict):
        parts = []
        if demographics.get("genders"):
            parts.append(", ".join(demographics["genders"]))
        if demographics.get("age_groups"):
            parts.append(f"Ages {', '.join(demographics['age_groups'])}")
        if demographics.get("household_income"):
            parts.append(f"HHI {', '.join(demographics['household_income'])}")
        if demographics.get("interests"):
            parts.append(f"Interests: {', '.join(demographics['interests'])}")
        if parts:
            out["demographics"] = " · ".join(parts)

    # Devices
    device_types = state.get("device_types") or []
    if device_types:
        out["devices"] = ", ".join(d.replace("_", " ").title() for d in device_types)

    return out
