import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MessageBubble } from "@/components/chat/MessageBubble";
import { textBlock } from "@/lib/chat";
import type { ChatMessage } from "@/types/chat";
import {
  elicitationProps,
  makeMessage,
  makeOptionsBlock,
} from "@/test/factories";

/** `messages` defaults to the turn itself — an answer resolves its labels by
 *  looking the elicitation up in the transcript, so it has to be reachable. */
function renderBubble(message: ChatMessage, transcript?: ChatMessage[]) {
  return render(
    <MessageBubble
      message={message}
      messages={transcript ?? [message]}
      {...elicitationProps()}
    />,
  );
}

describe("MessageBubble", () => {
  it("renders a user turn as a bubble at the inline end", () => {
    const { container } = renderBubble(
      makeMessage({ role: "user", content: [textBlock("first")] }),
    );

    expect(screen.getByText("first")).toBeInTheDocument();
    expect(container.querySelector(".justify-end")).not.toBeNull();
  });

  it("renders an assistant turn behind the brand mark, one paragraph per block", () => {
    const { container } = renderBubble(
      makeMessage({
        role: "assistant",
        content: [textBlock("first"), textBlock("second")],
      }),
    );

    expect(container.querySelector("svg")).not.toBeNull();
    expect([...container.querySelectorAll("p")].map((p) => p.textContent))
      .toEqual(["first", "second"]);
  });

  it("renders message content as plain text, never as markup", () => {
    // The no-dangerouslySetInnerHTML constraint in CLAUDE.md, as an assertion:
    // an agent reply is untrusted input and must never reach the DOM as HTML.
    const hostile = '<img src=x onerror=alert(1)><b>bold</b>';
    const { container } = renderBubble(
      makeMessage({ role: "assistant", content: [textBlock(hostile)] }),
    );

    expect(screen.getByText(hostile)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
  });

  it("preserves the newlines an agent uses to structure a plan", () => {
    const { container } = renderBubble(
      makeMessage({
        role: "assistant",
        content: [textBlock("Line one\n\nLine two")],
      }),
    );

    // Asserted on textContent rather than the whitespace-pre-wrap class: the
    // content surviving intact is the behaviour, the class is the mechanism.
    expect(container.textContent).toContain("Line one\n\nLine two");
  });

  it("renders an options block in an assistant turn as a labelled question", () => {
    const block = makeOptionsBlock();
    renderBubble(makeMessage({ role: "assistant", content: [block] }));

    expect(
      screen.getByRole("group", { name: block.prompt }),
    ).toBeInTheDocument();
    expect(screen.getByText("Prime Video")).toBeInTheDocument();
  });

  it("makes only the active question tappable", async () => {
    const block = makeOptionsBlock();
    const message = makeMessage({ role: "assistant", content: [block] });
    const onAnswer = vi.fn();

    const { rerender } = render(
      <MessageBubble
        message={message}
        messages={[message]}
        {...elicitationProps({ activeElicitationId: block.id, onAnswer })}
      />,
    );
    expect(screen.getByRole("button", { name: /Prime Video/ })).toBeEnabled();

    // Same block, no longer the active one: the rows stop being buttons.
    rerender(
      <MessageBubble
        message={message}
        messages={[message]}
        {...elicitationProps({ activeElicitationId: "other", onAnswer })}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /Prime Video/ }),
    ).not.toBeInTheDocument();
  });

  it("renders a recorded answer as its option labels, never as ids", () => {
    const block = makeOptionsBlock({ status: "answered" });
    const question = makeMessage({ role: "assistant", content: [block] });
    const answer = makeMessage({
      role: "user",
      content: [
        {
          type: "options_answer",
          elicitationId: block.id,
          selectedOptionIds: ["opt-prime", "opt-twitch"],
          customText: null,
        },
      ],
    });

    const { container } = renderBubble(answer, [question, answer]);

    expect(screen.getByText("Prime Video, Twitch")).toBeInTheDocument();
    expect(container.textContent).not.toContain("opt-prime");
  });

  it("never renders an options card inside a user turn", () => {
    // A user turn is text or a recorded answer; a question there contributes
    // nothing rather than becoming a second tappable card.
    const block = makeOptionsBlock();
    renderBubble(
      makeMessage({ role: "user", content: [textBlock("keep"), block] }),
    );

    expect(screen.getByText("keep")).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(screen.queryByText("Prime Video")).not.toBeInTheDocument();
  });

  it("notes a recorded answer echoed back in an assistant turn", () => {
    renderBubble(
      makeMessage({
        role: "assistant",
        content: [
          {
            type: "options_answer",
            elicitationId: "e-1",
            selectedOptionIds: ["opt-prime"],
            customText: null,
          },
        ],
      }),
    );

    expect(screen.getByText("Selection recorded")).toBeInTheDocument();
  });

  it("falls back to a recorded-selection note when no label resolves", () => {
    // The elicitation is absent from the transcript, so there is nothing to
    // resolve — the bubble must still say something rather than render empty.
    const answer = makeMessage({
      role: "user",
      content: [
        {
          type: "options_answer",
          elicitationId: "missing",
          selectedOptionIds: ["opt-prime"],
          customText: null,
        },
      ],
    });

    renderBubble(answer, [answer]);

    expect(screen.getByText("Selection recorded")).toBeInTheDocument();
  });
});
