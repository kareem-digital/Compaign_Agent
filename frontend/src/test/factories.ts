/**
 * Deterministic fixtures and stub transports shared by the co-located tests.
 * See `src/test/render.tsx` for why these live under `src/`.
 */
import { vi, type Mock } from "vitest";

import type { ElicitationSubmission } from "@/hooks/use-chat";
import type { AgentClient, AgentReply } from "@/lib/agent";
import { textBlock } from "@/lib/chat";
import type { ChatMessage, OptionsBlock } from "@/types/chat";
import type { ReachForecast, StrategyPlan } from "@/types/strategy";

let sequence = 0;

/**
 * A deterministic `ChatMessage`. Ids are sequential and the timestamp is a
 * fixed instant, so nothing in a rendered bubble drifts between runs.
 *
 * `content` is a block list, not a string — a turn is prose, a question or a
 * recorded answer. Pass `[textBlock("…")]` for the plain-prose case.
 */
export function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  sequence += 1;
  return {
    id: `message-${sequence}`,
    role: "user",
    content: [textBlock("Plan a CTV campaign for a Q4 product launch")],
    createdAt: Date.UTC(2024, 0, 1, 9, 30),
    ...overrides,
  };
}

/** A pending single-select question. `status` is server-owned, so a test that
 *  wants a closed row overrides it rather than expecting the UI to derive it. */
export function makeOptionsBlock(
  overrides: Partial<OptionsBlock> = {},
): OptionsBlock {
  return {
    type: "options",
    id: "elicitation-1",
    prompt: "Which inventory should the plan lean on?",
    select: "single",
    options: [
      { id: "opt-prime", label: "Prime Video", description: null, badge: null },
      {
        id: "opt-twitch",
        label: "Twitch",
        description: "Live sport and gaming",
        badge: "Suggested",
      },
    ],
    allowCustom: false,
    customPlaceholder: null,
    status: "pending",
    answer: null,
    ...overrides,
  };
}

/** The elicitation wiring `MessageBubble` and `MessageList` both require.
 *  Inert by default: nothing is answerable and nothing is in flight. */
export function elicitationProps(
  overrides: Partial<{
    activeElicitationId: string | null;
    submissions: Record<string, ElicitationSubmission>;
    onAnswer: Mock;
  }> = {},
) {
  return {
    activeElicitationId: null as string | null,
    submissions: {} as Record<string, ElicitationSubmission>,
    onAnswer: vi.fn(),
    ...overrides,
  };
}

/** A submission in flight. `state` is the only field most tests vary. */
export function makeSubmission(
  overrides: Partial<ElicitationSubmission> = {},
): ElicitationSubmission {
  return {
    clientMessageId: "client-1",
    optionIds: ["opt-prime"],
    customText: null,
    state: "submitting",
    ...overrides,
  };
}

/** A forecast small enough that tick and stat assertions stay readable. */
export function makeForecast(
  overrides: Partial<ReachForecast> = {},
): ReachForecast {
  return {
    stats: [
      { label: "Unique reach", value: "~2.4M" },
      { label: "Frequency", value: "3.2×" },
    ],
    curve: [
      { x: 0, y: 0 },
      { x: 0.5, y: 0.6 },
      { x: 1, y: 0.769 },
    ],
    ceiling: 1,
    ceilingLabel: "Addressable audience 3.5M",
    peakLabel: "~2.4M",
    axisLabels: { x: "Budget", y: "Unique reach" },
    xTicks: ["£0", "£24k", "£48k"],
    yTicks: ["0", "2M", "3.5M"],
    updatedLabel: "Updated just now",
    ...overrides,
  };
}

/**
 * A draft plan: one open stage carrying properties, one resting stage, one
 * locked stage, and no forecast — the state the workspace actually opens in.
 */
export function makePlan(overrides: Partial<StrategyPlan> = {}): StrategyPlan {
  return {
    name: "New strategy",
    status: "draft",
    completion: 15,
    stages: [
      {
        id: "basic-details",
        title: "Basic details",
        status: "in-progress",
        isOpen: true,
        properties: [
          { label: "Brand", value: "Mega Toothpaste" },
          { label: "Creative", value: null },
        ],
      },
      { id: "goals", title: "Goals, KPI & bid", status: "next" },
    ],
    lockedStages: [{ id: "creatives", title: "Creatives", status: "locked" }],
    forecast: null,
    ...overrides,
  };
}

export interface StubAgentClient extends AgentClient {
  send: Mock<AgentClient["send"]>;
}

/** Resolves immediately with `reply` as a single text block. `send` is a
 *  `vi.fn()`, so the usual `toHaveBeenCalledWith` assertions work unchanged. */
export function stubAgentClient(reply = "Here is a plan."): StubAgentClient {
  return {
    send: vi.fn<AgentClient["send"]>().mockResolvedValue({
      content: [textBlock(reply)],
    }),
  };
}

/**
 * Never lands until the caller aborts — for asserting in-flight states such as
 * the typing indicator and the disabled composer.
 */
export function pendingAgentClient(): StubAgentClient {
  return {
    send: vi.fn(
      (_request, options) =>
        new Promise<AgentReply>((_resolve, reject) => {
          options?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        }),
    ),
  };
}

/** Always fails, for the error-surface tests. */
export function failingAgentClient(cause: unknown): StubAgentClient {
  return { send: vi.fn<AgentClient["send"]>().mockRejectedValue(cause) };
}
