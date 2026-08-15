import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  isElicitationConflict,
  useAgentClient,
  type AgentRequest,
  type ElicitationConflictError,
  type PlanStage,
} from "@/lib/agent";
import { isAbortError } from "@/lib/api";
import {
  findActiveElicitation,
  matchesAnswer,
  replaceElicitationBlock,
  textBlock,
  validateSelection,
  type DraftSelection,
  type ValidationReason,
} from "@/lib/chat";
import { createId, normalizeInput } from "@/lib/utils";
import type {
  ChatMessage,
  ChatStatus,
  ElicitationStatus,
  MessageBlock,
  OptionsBlock,
  UserBlock,
} from "@/types/chat";

const TRANSPORT_ERROR = "The agent could not be reached. Please try again.";

const CONFLICT_MESSAGE: Record<ElicitationStatus, string> = {
  pending: "That question is no longer open.",
  answered: "That question was already answered.",
  superseded: "We've moved past that question.",
  expired: "That question is no longer open.",
};

const VALIDATION_MESSAGE: Record<ValidationReason, string> = {
  empty: "Choose an option or type an answer.",
  too_many: "That question takes a single choice.",
  custom_not_allowed: "That question doesn't accept a typed answer.",
  unknown_option: "That option is no longer available.",
};

/**
 * A tap that hasn't landed yet. Deliberately separate from
 * `OptionsBlock.status`, which is the server's to own — so a spinner never
 * implies a lock, and a lock never implies a spinner.
 */
export interface ElicitationSubmission {
  /** Reused verbatim on retry, so the server recognises the repeat. */
  clientMessageId: string;
  optionIds: string[];
  customText: string | null;
  state: "submitting" | "failed";
  error?: string;
}

export type SubmissionMap = Record<string, ElicitationSubmission>;

/** What we sent, for comparing against whatever the server ends up recording. */
interface AnsweredContext {
  elicitationId: string;
  optionIds: string[];
  customText: string | null;
}

function createMessage(
  role: ChatMessage["role"],
  content: MessageBlock[],
  clientMessageId?: string,
): ChatMessage {
  return {
    id: createId(),
    role,
    content,
    createdAt: Date.now(),
    clientMessageId,
  };
}

/** Local conversation state. Nothing is persisted — this is per-mount only. */
export function useChat() {
  // Injected rather than imported, so the transport can be stubbed in tests
  // and overridden by a host application.
  const agentClient = useAgentClient();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<PlanStage | null>(null);
  const [submissions, setSubmissions] = useState<SubmissionMap>({});

  // The ref is authoritative: `answerElicitation` has to read the previous
  // attempt's idempotency key before the next render lands.
  const submissionsRef = useRef<SubmissionMap>(submissions);
  const writeSubmissions = useCallback(
    (mutate: (previous: SubmissionMap) => SubmissionMap) => {
      submissionsRef.current = mutate(submissionsRef.current);
      setSubmissions(submissionsRef.current);
    },
    [],
  );

  const abortRef = useRef<AbortController | null>(null);
  const isSendingRef = useRef(false);

  useEffect(() => () => abortRef.current?.abort(), []);

  const dropSubmission = useCallback(
    (elicitationId: string) =>
      writeSubmissions(({ [elicitationId]: _removed, ...rest }) => rest),
    [writeSubmissions],
  );

  /**
   * The server refused because the row isn't pending. Its state wins outright; a
   * recorded answer matching ours is just our own double-submit landing twice,
   * so that case is corrected silently rather than reported as a failure.
   */
  const reconcile = useCallback(
    (
      conflict: ElicitationConflictError,
      answered: AnsweredContext,
      optimisticId: string,
    ) => {
      const server = conflict.elicitation;
      const ours = matchesAnswer(server.answer, answered);

      setMessages((previous) => {
        const patched = replaceElicitationBlock(previous, server);
        return ours
          ? patched
          : patched.filter((message) => message.id !== optimisticId);
      });
      if (!ours) setError(CONFLICT_MESSAGE[server.status]);
      // Never retried: the same request would conflict again.
      dropSubmission(answered.elicitationId);
    },
    [dropSubmission],
  );

  const submit = useCallback(
    async (
      request: AgentRequest,
      optimistic: ChatMessage,
      answered?: AnsweredContext,
    ) => {
      isSendingRef.current = true;
      setError(null);
      setStatus("sending");
      setMessages((previous) => [...previous, optimistic]);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const reply = await agentClient.send(request, {
          signal: controller.signal,
        });

        setMessages((previous) => [
          // Status and recorded selection come from the reply, never from the
          // tap — including for questions sitting in earlier messages.
          ...(reply.resolvedElicitations ?? []).reduce(
            replaceElicitationBlock,
            previous,
          ),
          createMessage("assistant", reply.content),
        ]);
        setStage(reply.stage ?? null);
        if (answered) dropSubmission(answered.elicitationId);
      } catch (cause) {
        // Cancellation is control flow — reset and unmount both abort.
        if (isAbortError(cause)) return;

        if (!answered) {
          // A typed turn keeps its bubble: the text is still what the user said.
          setError(TRANSPORT_ERROR);
          return;
        }
        if (isElicitationConflict(cause)) {
          reconcile(cause, answered, optimistic.id);
          return;
        }

        // The row is still pending server-side, so drop the bubble and leave the
        // card answerable — with the same key, so a retry replays server-side.
        setMessages((previous) =>
          previous.filter((message) => message.id !== optimistic.id),
        );
        setError(TRANSPORT_ERROR);
        writeSubmissions((previous) => ({
          ...previous,
          [answered.elicitationId]: {
            ...previous[answered.elicitationId],
            state: "failed",
            error: TRANSPORT_ERROR,
          },
        }));
      } finally {
        isSendingRef.current = false;
        abortRef.current = null;
        setStatus("idle");
      }
    },
    [agentClient, dropSubmission, reconcile, writeSubmissions],
  );

  const send = useCallback(
    async (rawInput: string) => {
      const content = normalizeInput(rawInput);
      if (!content || isSendingRef.current) return;

      const clientMessageId = createId();
      const blocks: UserBlock[] = [textBlock(content)];
      await submit(
        { clientMessageId, content: blocks },
        createMessage("user", blocks, clientMessageId),
      );
    },
    [submit],
  );

  /**
   * Answers a question. Takes the block the user tapped rather than an id, so
   * there is nothing to look up and nothing to go stale between the two.
   */
  const answerElicitation = useCallback(
    async (block: OptionsBlock, draft: DraftSelection) => {
      // Also what stops a double-tap becoming two requests, and what keeps the
      // card's inline field and the composer from both landing an answer.
      if (isSendingRef.current) return;

      const result = validateSelection(block, draft);
      if (!result.ok) {
        setError(VALIDATION_MESSAGE[result.reason]);
        return;
      }

      const answer = result.answer;
      const answered: AnsweredContext = {
        elicitationId: block.id,
        optionIds: answer.selectedOptionIds,
        customText: answer.customText ?? null,
      };
      // A retry reuses the original key, so the server replays rather than
      // recording the same answer twice.
      const clientMessageId =
        submissionsRef.current[block.id]?.clientMessageId ?? createId();

      writeSubmissions((previous) => ({
        ...previous,
        [block.id]: { ...answered, clientMessageId, state: "submitting" },
      }));

      await submit(
        { clientMessageId, content: [answer] },
        createMessage("user", [answer], clientMessageId),
        answered,
      );
    },
    [submit, writeSubmissions],
  );

  // Clears the local transcript only. The session id lives on the client
  // instance, so the server-side conversation continues until that is rebuilt.
  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    isSendingRef.current = false;
    setMessages([]);
    setError(null);
    setStatus("idle");
    setStage(null);
    writeSubmissions(() => ({}));
  }, [writeSubmissions]);

  /** The one answerable question, derived from what the server sent. */
  const activeElicitation = useMemo(
    () => findActiveElicitation(messages)?.block ?? null,
    [messages],
  );

  return {
    messages,
    status,
    error,
    stage,
    isSending: status === "sending",
    activeElicitation,
    submissions,
    send,
    answerElicitation,
    reset,
  };
}
