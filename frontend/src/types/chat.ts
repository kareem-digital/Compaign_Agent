/** Domain types for the chat experience. Kept transport-agnostic and
 *  serializable so nothing above the API layer depends on the wire format. */

export type MessageRole = "user" | "assistant";

export interface TextBlock {
  type: "text";
  text: string;
}

export type ElicitationSelect = "single" | "multi";

/** Server-owned lifecycle. The client renders it and never derives it. */
export type ElicitationStatus =
  | "pending"
  | "answered"
  | "superseded"
  | "expired";

export interface OptionChoice {
  id: string;
  /** Human-facing. The only option text the client ever renders. */
  label: string;
  description?: string | null;
  /** Short server-supplied tag drawn as a pill — "Suggested", "Ran last year". */
  badge?: string | null;
}

export interface ElicitationAnswer {
  selectedOptionIds: string[];
  customText?: string | null;
  /** Epoch milliseconds, or null when the server did not say. */
  answeredAt?: number | null;
}

export interface OptionsBlock {
  type: "options";
  /** Server-side elicitation row id; the answer's foreign key. */
  id: string;
  prompt: string;
  select: ElicitationSelect;
  options: OptionChoice[];
  /** Whether a typed answer in the composer resolves this question. */
  allowCustom: boolean;
  customPlaceholder?: string | null;
  /** Server-owned. Never written locally, not even optimistically. */
  status: ElicitationStatus;
  /** What the server recorded. Present once the status is `answered`. */
  answer?: ElicitationAnswer | null;
}

/** A recorded answer as it appears in the user's own turn. IDs only. */
export interface OptionsAnswerBlock {
  type: "options_answer";
  elicitationId: string;
  selectedOptionIds: string[];
  customText?: string | null;
}

export type MessageBlock = TextBlock | OptionsBlock | OptionsAnswerBlock;

/** Blocks a user turn can carry. */
export type UserBlock = TextBlock | OptionsAnswerBlock;

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: MessageBlock[];
  /** Epoch milliseconds — serializable, formatted at render time. */
  createdAt: number;
  /** Idempotency key. Set on user turns only. */
  clientMessageId?: string;
}

export type ChatStatus = "idle" | "sending";
