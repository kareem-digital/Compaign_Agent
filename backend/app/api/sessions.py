import logging
import time
import uuid

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.agent.checkpointer import create_checkpointer
from app.agent.graph import build_graph
from app.api.presentation import Block, build_blocks
from app.config import get_settings
from app.core.context import bind
from app.core.exceptions import (
    AdvertiserContextMissingError,
    KillSwitchEngagedError,
    MCPError,
    PolicyDeniedError,
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


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Send the same ID to continue a conversation; omit to start new.",
    )


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    stage: str | None = Field(
        None, description="Stage the plan reached on this turn, e.g. 'forecast'."
    )
    blocks: list[Block] = Field(
        default_factory=list,
        description=(
            "The reply broken into renderable pieces. Each says what it is, how "
            "it should appear, and carries the data behind it. `reply` remains "
            "the plain-text equivalent."
        ),
    )


class SessionState(BaseModel):
    session_id: str
    message_count: int
    stage: str | None = None
    next_node: list[str] | None = None


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
    vowmade_advertiser_id: str | None = Header(None, alias="Vowmade-Advertiser-Id"),
):
    advertiser_id = _resolve_advertiser(vowmade_advertiser_id)
    bind(session_id=request.session_id, advertiser_id=advertiser_id)

    graph = await _get_graph(advertiser_id)
    thread_config = {"configurable": {"thread_id": request.session_id}}

    # Message count before this turn, so we can return only what this turn said
    # rather than the whole transcript.
    prior = await graph.aget_state(thread_config)
    prior_count = len(prior.values.get("messages", [])) if prior and prior.values else 0

    started = time.monotonic()
    logger.info(
        "turn.start",
        extra=kv(turn=(prior_count // 5) + 1, message_chars=len(request.message)),
    )
    # The brief itself is client-commercial data, so content stays at DEBUG.
    logger.debug("turn.message", extra=kv(text=request.message))

    try:
        result = await graph.ainvoke(
            {
                "messages": [{"role": "user", "content": request.message}],
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

    # The graph runs several nodes per turn and each one speaks. Joined into one
    # string so the transport contract stays a single reply.
    return ChatResponse(
        session_id=request.session_id,
        reply="\n\n".join(r for r in replies if r),
        stage=result.get("current_stage"),
        blocks=build_blocks(result),
    )


@router.get("/{session_id}", response_model=SessionState)
async def get_session(
    session_id: str,
    vowmade_advertiser_id: str | None = Header(None, alias="Vowmade-Advertiser-Id"),
):
    advertiser_id = _resolve_advertiser(vowmade_advertiser_id)
    graph = await _get_graph(advertiser_id)
    thread_config = {"configurable": {"thread_id": session_id}}

    try:
        state = await graph.aget_state(thread_config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found") from exc

    if not state or not state.values:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return SessionState(
        session_id=session_id,
        message_count=len(state.values.get("messages", [])),
        stage=state.values.get("current_stage"),
        next_node=list(state.next) if state.next else None,
    )
