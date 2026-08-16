import { ElicitationConflictError } from "@/lib/agent/errors";
import type {
  AgentClient,
  AgentReply,
  AgentRequest,
  SendOptions,
} from "@/lib/agent/types";
import type {
  WireBlock,
  WireChatRequest,
  WireChatResponse,
  WireElicitationAnswer,
  WireElicitationConflictBody,
  WireOptionsBlock,
} from "@/lib/agent/wire";
import { ApiError, createHttpClient } from "@/lib/api";
import { blocksToPlainText, textBlock } from "@/lib/chat";
import type { AppConfig } from "@/lib/config";
import { createId } from "@/lib/utils";
import type {
  ElicitationAnswer,
  ElicitationStatus,
  MessageBlock,
  OptionsBlock,
  UserBlock,
} from "@/types/chat";

export interface HttpAgentClientOptions {
  /** Injectable for tests; defaults to the global fetch. */
  fetchImpl?: typeof fetch;
}

// TEMP: hardcoded advertiser context. Map to the host's real advertiser later.
const ADVERTISER_ID = "dev-advertiser-0001";

const STATUSES: ElicitationStatus[] = [
  "pending",
  "answered",
  "superseded",
  "expired",
];

/** Anything unrecognized fails closed: a dead row must never look answerable. */
function toStatus(value: string): ElicitationStatus {
  return STATUSES.find((status) => status === value) ?? "expired";
}

function toEpoch(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function toAnswer(
  wire: WireElicitationAnswer | null | undefined,
): ElicitationAnswer | null {
  if (!wire) return null;
  return {
    selectedOptionIds: wire.selected_option_ids ?? [],
    customText: wire.custom_text ?? null,
    answeredAt: toEpoch(wire.answered_at),
  };
}

/**
 * Fields are copied one by one rather than spread, so a model-facing `value` a
 * server sends anyway cannot cross the boundary into the app.
 */
function toOptionsBlock(wire: WireOptionsBlock): OptionsBlock {
  return {
    type: "options",
    id: wire.id,
    prompt: wire.prompt,
    select: wire.select === "multi" ? "multi" : "single",
    options: (wire.options ?? []).map((option) => ({
      id: option.id,
      label: option.label,
      description: option.description ?? null,
      badge: option.badge ?? null,
    })),
    allowCustom: wire.allow_custom ?? false,
    customPlaceholder: wire.custom_placeholder ?? null,
    status: toStatus(wire.status),
    answer: toAnswer(wire.answer),
  };
}

/** Unknown block types map to null and are dropped, so a block this client does
 *  not understand degrades to "not rendered" instead of breaking the turn. */
function toDomainBlock(wire: WireBlock): MessageBlock | null {
  switch (wire.type) {
    case "text":
      return textBlock(wire.text);
    case "options":
      return toOptionsBlock(wire);
    case "options_response":
      return {
        type: "options_answer",
        elicitationId: wire.elicitation_id,
        selectedOptionIds: wire.selected_option_ids ?? [],
        customText: wire.custom_text ?? null,
      };
    default:
      return null;
  }
}

function backendBlockToDomainBlock(block: any): MessageBlock | null {
  if (!block) return null;

  if (
    block.interaction === "input_date_range" ||
    block.layout === "date_range_picker" ||
    block.field === "flight_dates"
  ) {
    return {
      type: "date_picker",
      id: block.field || createId(),
      prompt: block.text || "When should the campaign run?",
      earliest: block.data?.earliest || new Date().toISOString().split("T")[0],
      status: "pending",
    };
  }

  if (
    block.interaction === "select_one" ||
    block.interaction === "select_many" ||
    block.interaction === "confirm"
  ) {
    let rawOptions = block.data?.options ?? [];
    if (
      rawOptions.length === 0 &&
      block.data?.rows &&
      Array.isArray(block.data.rows)
    ) {
      rawOptions = block.data.rows.map((row: any) => ({
        value: row.provider
          ? `${row.provider}${row.genre && row.genre !== "Run of service" ? ` (${row.genre})` : ""}`
          : row.value || row.label,
        label: row.provider
          ? `${row.provider}${row.genre && row.genre !== "Run of service" ? ` (${row.genre})` : ""}`
          : row.label || row.value,
        description: `Indicative CPM: £${row.cpm}${row.lengths ? ` (${row.lengths})` : ""}${row.tier ? ` · ${row.tier}` : ""}`,
        badge: row.tier?.includes("Amazon") ? "Amazon-owned" : null,
        recommended: Boolean(row.selected),
      }));
    }

    const options = rawOptions.map((opt: any) => {
      let desc = opt.sublabel || opt.description || null;
      if (opt.metrics && typeof opt.metrics === "object") {
        const metricStr = Object.entries(opt.metrics)
          .filter(([, v]) => v != null)
          .map(([k, v]) => `${k}: ${v}`)
          .join(" • ");
        desc = desc ? `${desc} (${metricStr})` : metricStr;
      }
      return {
        id: String(opt.value || opt.id || opt.label),
        label: String(opt.label || opt.name || opt.value),
        description: desc,
        badge: opt.badge || (opt.recommended ? "Recommended" : null),
      };
    });

    if (options.length > 0) {
      return {
        type: "options",
        id: block.field || createId(),
        prompt: block.text || "Please select an option:",
        select: block.interaction === "select_many" ? "multi" : "single",
        options,
        allowCustom: false,
        status: "pending",
      };
    }
  }
  return textBlock(block.text);
}

/** Blocks when the server speaks them, else the legacy `reply` string. */
function toReplyBlocks(payload: WireChatResponse): MessageBlock[] {
  if (payload.blocks && Array.isArray(payload.blocks) && payload.blocks.length > 0) {
    const converted = payload.blocks
      .map(backendBlockToDomainBlock)
      .filter((block): block is MessageBlock => block !== null);
    if (converted.length > 0) {
      return converted;
    }
  }
  const blocks = (payload.message?.content ?? [])
    .map(toDomainBlock)
    .filter((block): block is MessageBlock => block !== null);
  if (blocks.length) return blocks;
  return payload.reply ? [textBlock(payload.reply)] : [];
}

/** Convert the always-present plan_state map to the planRows array format. */
function extractPlanState(
  payload: WireChatResponse,
): Array<{ label: string; value: string; field: string }> | undefined {
  const planState = payload.plan_state;
  if (!planState || Object.keys(planState).length === 0) return undefined;

  // Label map matching the Strategy Schema sections.
  const LABELS: Record<string, string> = {
    brand: "Brand",
    markets: "Markets",
    flight_dates: "Flight",
    durations: "Creative durations",
    market_budgets: "Budget",
    goal: "Goal",
    kpi: "KPI",
    bid: "Bid",
    inventory: "CTV inventory",
    audience: "Audience profile",
    targeting: "Targeting",
  };

  return Object.entries(planState)
    .filter(([field]) => field in LABELS)
    .map(([field, value]) => ({
      field,
      label: LABELS[field] ?? field,
      value,
    }));
}

function toWireBlock(block: UserBlock): WireBlock {
  if (block.type === "text") return { type: "text", text: block.text };
  return {
    type: "options_response",
    elicitation_id: block.elicitationId,
    selected_option_ids: block.selectedOptionIds,
    custom_text: block.customText ?? null,
  };
}

/** 409 → a typed domain error. An unrecognizable body stays an `ApiError`. */
function asConflict(cause: unknown): ElicitationConflictError | null {
  if (!(cause instanceof ApiError) || cause.status !== 409) return null;
  const body = cause.body as WireElicitationConflictBody | undefined;
  if (!body?.elicitation) return null;
  return new ElicitationConflictError(toOptionsBlock(body.elicitation), {
    requestId: cause.requestId,
    cause,
  });
}

/**
 * The FastAPI transport. `AgentRequest`/`AgentReply` ↔ wire mapping lives here
 * and nowhere else, so the rest of the app stays ignorant of the wire format.
 *
 * The backend keeps conversation state server-side, keyed by `session_id`. One
 * client instance is one conversation — it mints the id once below and reuses it
 * for every turn, so the one-instance-per-mount lifecycle in
 * `agent-client-context.tsx` is what gives a new chat a new session.
 */
export function createHttpAgentClient(
  cfg: AppConfig,
  options: HttpAgentClientOptions = {},
): AgentClient {
  const http = createHttpClient({
    baseUrl: cfg.apiBaseUrl,
    timeoutMs: cfg.requestTimeoutMs,
    fetchImpl: options.fetchImpl,
  });

  // TEMP: minted locally because the endpoint that issues a session id isn't
  // live yet. Swap for the server-issued id once that lands.
  const sessionId = createId();

  return {
    async send(
      request: AgentRequest,
      sendOptions?: SendOptions,
    ): Promise<AgentReply> {
      // `message` is the plain-text projection today's backend reads. It covers
      // text blocks only, so an answer-only turn omits it rather than pushing
      // option labels into a field that becomes prompt context.
      const body: WireChatRequest = {
        session_id: sessionId,
        client_message_id: request.clientMessageId,
        message: blocksToPlainText(request.content) || undefined,
        content: request.content.map(toWireBlock),
      };

      let payload: WireChatResponse;
      try {
        payload = await http.request<WireChatResponse>("/sessions/chat", {
          method: "POST",
          body,
          headers: { "Vowmade-Advertiser-Id": ADVERTISER_ID },
          signal: sendOptions?.signal,
        });
      } catch (cause) {
        throw asConflict(cause) ?? cause;
      }

      return {
        messageId: payload.message?.id,
        content: toReplyBlocks(payload),
        stage: payload.stage ?? null,
        resolvedElicitations: (payload.resolved_elicitations ?? []).map(
          toOptionsBlock,
        ),
        planRows: extractPlanState(payload),
      };
    },
  };
}
