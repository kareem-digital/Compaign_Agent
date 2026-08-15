import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useChat } from "@/hooks/use-chat";
import {
  ElicitationConflictError,
  type AgentClient,
  type AgentReply,
} from "@/lib/agent";
import { ApiError } from "@/lib/api";
import { textBlock } from "@/lib/chat";
/**
 * The transport is injected, not module-mocked — that injectability is the
 * property these tests are really guarding.
 */
import { agentWrapper as wrapperFor } from "@/test/render";
import {
  makeOptionsBlock,
  pendingAgentClient,
  stubAgentClient,
} from "@/test/factories";

describe("useChat", () => {
  it("appends the user message and the agent reply", async () => {
    const client = stubAgentClient("Here is a plan.");
    const { result } = renderHook(() => useChat(), {
      wrapper: wrapperFor(client),
    });

    await act(async () => {
      await result.current.send("Plan a CTV campaign");
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0]).toMatchObject({
      role: "user",
      content: [{ type: "text", text: "Plan a CTV campaign" }],
    });
    expect(result.current.messages[1]).toMatchObject({
      role: "assistant",
      content: [{ type: "text", text: "Here is a plan." }],
    });
    expect(result.current.isSending).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("sends the turn's blocks and an abort signal, never local history", async () => {
    // The backend keeps conversation state server-side keyed by the session id,
    // so `AgentRequest` deliberately carries no `history` — serializing local
    // state back to the server that owns it is the bug this design prevents.
    const client = stubAgentClient("ok");
    const { result } = renderHook(() => useChat(), {
      wrapper: wrapperFor(client),
    });

    await act(async () => {
      await result.current.send("first");
    });
    await act(async () => {
      await result.current.send("second");
    });

    expect(client.send).toHaveBeenLastCalledWith(
      {
        clientMessageId: expect.any(String),
        content: [textBlock("second")],
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(client.send.mock.calls[1][0]).not.toHaveProperty("history");
  });

  it("gives each turn its own idempotency key", async () => {
    const client = stubAgentClient();
    const { result } = renderHook(() => useChat(), {
      wrapper: wrapperFor(client),
    });

    await act(async () => {
      await result.current.send("first");
    });
    await act(async () => {
      await result.current.send("second");
    });

    const [first, second] = client.send.mock.calls.map(
      ([request]) => request.clientMessageId,
    );
    expect(first).toBeTruthy();
    expect(second).not.toBe(first);
  });

  it("surfaces a friendly error when the transport fails", async () => {
    const client: AgentClient = {
      send: vi.fn().mockRejectedValue(new ApiError("boom", { status: 500 })),
    };
    const { result } = renderHook(() => useChat(), {
      wrapper: wrapperFor(client),
    });

    await act(async () => {
      await result.current.send("Plan a CTV campaign");
    });

    expect(result.current.error).toBe(
      "The agent could not be reached. Please try again.",
    );
    // The user's own message stays; only the reply is missing.
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.isSending).toBe(false);
  });

  it("ignores blank input without calling the transport", async () => {
    const client = stubAgentClient();
    const { result } = renderHook(() => useChat(), {
      wrapper: wrapperFor(client),
    });

    await act(async () => {
      await result.current.send("   \n  ");
    });

    expect(client.send).not.toHaveBeenCalled();
    expect(result.current.messages).toHaveLength(0);
  });

  it("aborts an in-flight request on reset without raising an error", async () => {
    const client = pendingAgentClient();
    const { result } = renderHook(() => useChat(), {
      wrapper: wrapperFor(client),
    });

    let pending!: Promise<void>;
    await act(async () => {
      pending = result.current.send("Plan a CTV campaign");
    });
    await waitFor(() => expect(result.current.isSending).toBe(true));

    await act(async () => {
      result.current.reset();
      await pending;
    });

    expect(result.current.messages).toHaveLength(0);
    expect(result.current.error).toBeNull();
    expect(result.current.isSending).toBe(false);
  });

  it("tracks the stage the reply reports and clears it on reset", async () => {
    const client: AgentClient = {
      send: vi.fn().mockResolvedValue({
        content: [textBlock("Noted.")],
        stage: "inventory",
      }),
    };
    const { result } = renderHook(() => useChat(), {
      wrapper: wrapperFor(client),
    });

    await act(async () => {
      await result.current.send("plan a campaign");
    });
    expect(result.current.stage).toBe("inventory");

    act(() => result.current.reset());

    expect(result.current.stage).toBeNull();
    expect(result.current.messages).toHaveLength(0);
    expect(result.current.submissions).toEqual({});
  });

  it("ignores a second turn while one is still in flight", async () => {
    const client = pendingAgentClient();
    const { result } = renderHook(() => useChat(), {
      wrapper: wrapperFor(client),
    });

    let pending!: Promise<void>;
    await act(async () => {
      pending = result.current.send("first");
    });
    await waitFor(() => expect(result.current.isSending).toBe(true));

    await act(async () => {
      await result.current.send("second");
    });

    expect(client.send).toHaveBeenCalledOnce();

    await act(async () => {
      result.current.reset();
      await pending;
    });
  });
});

/**
 * The elicitation half of the hook. Every case below starts from a transcript
 * where the agent has asked a question, because that is the only state in which
 * an answer is meaningful.
 */
describe("useChat — answering an elicitation", () => {
  const TRANSPORT_ERROR = "The agent could not be reached. Please try again.";
  const question = makeOptionsBlock();
  const chose = { optionIds: ["opt-prime"], customText: "" };

  /** The recorded answer as the server would hand it back. */
  const recorded = (selectedOptionIds: string[], customText: string | null = null) => ({
    selectedOptionIds,
    customText,
    answeredAt: null,
  });

  /** Runs the first turn so the question is sitting in the transcript. */
  async function openQuestion(send: AgentClient["send"]) {
    const { result } = renderHook(() => useChat(), {
      wrapper: wrapperFor({ send }),
    });
    await act(async () => {
      await result.current.send("plan a campaign");
    });
    expect(result.current.activeElicitation).toEqual(question);
    return result;
  }

  const asking = () =>
    vi
      .fn<AgentClient["send"]>()
      .mockResolvedValueOnce({ content: [question] });

  it("submits ids only, then closes the question from the server's record", async () => {
    const send = asking().mockResolvedValueOnce({
      content: [textBlock("Noted.")],
      resolvedElicitations: [
        makeOptionsBlock({
          status: "answered",
          answer: recorded(["opt-prime"]),
        }),
      ],
    });
    const result = await openQuestion(send);

    await act(async () => {
      await result.current.answerElicitation(question, chose);
    });

    // Labels never cross the boundary — the answer carries ids.
    expect(send).toHaveBeenLastCalledWith(
      {
        clientMessageId: expect.any(String),
        content: [
          {
            type: "options_answer",
            elicitationId: question.id,
            selectedOptionIds: ["opt-prime"],
            customText: null,
          },
        ],
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    // user turn, question, the answer bubble, the follow-up.
    expect(result.current.messages).toHaveLength(4);
    // Closed by the server's status, not by the tap.
    expect(result.current.activeElicitation).toBeNull();
    expect(result.current.submissions).toEqual({});
    expect(result.current.error).toBeNull();
  });

  it("normalizes a typed answer and sends it in place of ids", async () => {
    const custom = makeOptionsBlock({ allowCustom: true });
    const send = vi
      .fn<AgentClient["send"]>()
      .mockResolvedValueOnce({ content: [custom] })
      .mockResolvedValueOnce({ content: [textBlock("Noted.")] });
    const { result } = renderHook(() => useChat(), {
      wrapper: wrapperFor({ send }),
    });
    await act(async () => {
      await result.current.send("plan a campaign");
    });

    await act(async () => {
      await result.current.answerElicitation(custom, {
        optionIds: [],
        customText: "  Freevee  ",
      });
    });

    expect(send.mock.calls[1][0].content).toEqual([
      {
        type: "options_answer",
        elicitationId: custom.id,
        selectedOptionIds: [],
        customText: "Freevee",
      },
    ]);
  });

  it.each([
    [{ optionIds: [], customText: "" }, "Choose an option or type an answer."],
    [
      { optionIds: ["opt-prime", "opt-twitch"], customText: "" },
      "That question takes a single choice.",
    ],
    [
      { optionIds: [], customText: "something else" },
      "That question doesn't accept a typed answer.",
    ],
    [
      { optionIds: ["opt-ghost"], customText: "" },
      "That option is no longer available.",
    ],
  ])("refuses an invalid answer without reaching the transport", async (draft, message) => {
    const send = asking();
    const result = await openQuestion(send);

    await act(async () => {
      await result.current.answerElicitation(question, draft);
    });

    expect(result.current.error).toBe(message);
    expect(send).toHaveBeenCalledOnce();
    // Still open, so the user can correct the selection.
    expect(result.current.activeElicitation).toEqual(question);
  });

  it("corrects a conflict silently when the server recorded our own answer", async () => {
    // A 409 whose record matches is our double-submit landing twice, not a
    // stale tab — so the bubble stays and nothing is reported.
    const server = makeOptionsBlock({
      status: "answered",
      answer: recorded(["opt-prime"]),
    });
    const send = asking().mockRejectedValueOnce(
      new ElicitationConflictError(server),
    );
    const result = await openQuestion(send);

    await act(async () => {
      await result.current.answerElicitation(question, chose);
    });

    expect(result.current.error).toBeNull();
    expect(result.current.messages).toHaveLength(3);
    expect(result.current.activeElicitation).toBeNull();
    expect(result.current.submissions).toEqual({});
  });

  it.each([
    ["answered", "That question was already answered."],
    ["superseded", "We've moved past that question."],
    ["expired", "That question is no longer open."],
  ] as const)(
    "drops the bubble and explains a %s conflict that is not ours",
    async (status, message) => {
      const send = asking().mockRejectedValueOnce(
        new ElicitationConflictError(
          makeOptionsBlock({ status, answer: recorded(["opt-twitch"]) }),
        ),
      );
      const result = await openQuestion(send);

      await act(async () => {
        await result.current.answerElicitation(question, chose);
      });

      expect(result.current.error).toBe(message);
      // The optimistic bubble is gone: we did not say that.
      expect(result.current.messages).toHaveLength(2);
      expect(result.current.submissions).toEqual({});
    },
  );

  it("leaves the question answerable after a transport failure, and retries with the same key", async () => {
    const send = asking()
      .mockRejectedValueOnce(new ApiError("boom", { status: 500 }))
      .mockResolvedValueOnce({ content: [textBlock("Noted.")] });
    const result = await openQuestion(send);

    await act(async () => {
      await result.current.answerElicitation(question, chose);
    });

    expect(result.current.error).toBe(TRANSPORT_ERROR);
    // Bubble dropped, but the row is still pending server-side.
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.activeElicitation).toEqual(question);
    expect(result.current.submissions[question.id]).toMatchObject({
      state: "failed",
      error: TRANSPORT_ERROR,
    });

    const firstKey = send.mock.calls[1][0].clientMessageId;
    await act(async () => {
      await result.current.answerElicitation(question, chose);
    });

    // The same key, so the server replays rather than recording twice.
    expect(send.mock.calls[2][0].clientMessageId).toBe(firstKey);
    expect(result.current.submissions).toEqual({});
  });

  it("marks the tap in flight and ignores a second one until it lands", async () => {
    let settle!: (reply: AgentReply) => void;
    const send = asking().mockImplementationOnce(
      () =>
        new Promise<AgentReply>((resolve) => {
          settle = resolve;
        }),
    );
    const result = await openQuestion(send);

    let pending!: Promise<void>;
    await act(async () => {
      pending = result.current.answerElicitation(question, chose);
    });
    await waitFor(() => expect(result.current.isSending).toBe(true));

    expect(result.current.submissions[question.id]).toMatchObject({
      state: "submitting",
      optionIds: ["opt-prime"],
    });

    // A double-tap, or the composer landing an answer at the same time.
    await act(async () => {
      await result.current.answerElicitation(question, {
        optionIds: ["opt-twitch"],
        customText: "",
      });
    });
    expect(send).toHaveBeenCalledTimes(2);

    await act(async () => {
      settle({ content: [textBlock("Noted.")] });
      await pending;
    });

    expect(result.current.submissions).toEqual({});
  });

  it("patches a question sitting in an earlier message", async () => {
    // The answered row lives two turns back, so only `resolvedElicitations`
    // can close it — the client never decides that for itself.
    const send = asking()
      .mockResolvedValueOnce({ content: [textBlock("Thinking…")] })
      .mockResolvedValueOnce({
        content: [textBlock("Noted.")],
        resolvedElicitations: [
          makeOptionsBlock({ status: "superseded", answer: recorded([]) }),
        ],
      });
    const result = await openQuestion(send);

    await act(async () => {
      await result.current.send("actually, wait");
    });
    expect(result.current.activeElicitation).toEqual(question);

    await act(async () => {
      await result.current.send("go on");
    });

    expect(result.current.activeElicitation).toBeNull();
  });
});
