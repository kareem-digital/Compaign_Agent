import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MessageList } from "@/components/chat/MessageList";
import { textBlock } from "@/lib/chat";
import { elicitationProps, makeMessage } from "@/test/factories";

afterEach(() => {
  vi.restoreAllMocks();
});

const text = (value: string) => makeMessage({ content: [textBlock(value)] });

describe("MessageList", () => {
  it("renders every message in order", () => {
    const messages = [
      makeMessage({ role: "user", content: [textBlock("first")] }),
      makeMessage({ role: "assistant", content: [textBlock("second")] }),
      makeMessage({ role: "user", content: [textBlock("third")] }),
    ];

    render(
      <MessageList
        messages={messages}
        isSending={false}
        {...elicitationProps()}
      />,
    );

    const rendered = screen
      .getAllByText(/first|second|third/)
      .map((node) => node.textContent);
    expect(rendered).toEqual(["first", "second", "third"]);
  });

  it("labels the conversation as a live log for assistive technology", () => {
    render(
      <MessageList
        messages={[makeMessage()]}
        isSending={false}
        {...elicitationProps()}
      />,
    );

    const log = screen.getByRole("log", { name: "Conversation" });
    expect(log).toHaveAttribute("aria-live", "polite");
  });

  it("shows the typing indicator only while a reply is in flight", () => {
    const props = elicitationProps();
    const { rerender } = render(
      <MessageList messages={[makeMessage()]} isSending={false} {...props} />,
    );
    expect(
      screen.queryByLabelText("VOW Agent is typing"),
    ).not.toBeInTheDocument();

    rerender(<MessageList messages={[makeMessage()]} isSending {...props} />);

    expect(screen.getByLabelText("VOW Agent is typing")).toBeInTheDocument();
    // The dots are decorative; this is what a screen reader announces.
    expect(screen.getByText("Thinking…")).toBeInTheDocument();
  });

  it("scrolls to the newest message whenever the list changes", () => {
    // jsdom does not implement scrollIntoView; setupTests.ts installs the no-op
    // that this spies on.
    const scrollIntoView = vi.spyOn(Element.prototype, "scrollIntoView");
    const props = elicitationProps();
    const first = text("first");

    const { rerender } = render(
      <MessageList messages={[first]} isSending={false} {...props} />,
    );

    expect(scrollIntoView).toHaveBeenCalledWith({
      block: "end",
      behavior: "smooth",
    });

    scrollIntoView.mockClear();
    rerender(
      <MessageList
        messages={[first, text("second")]}
        isSending={false}
        {...props}
      />,
    );

    expect(scrollIntoView).toHaveBeenCalledOnce();
  });

  it("scrolls when the typing indicator appears, so it is not hidden below the fold", () => {
    const scrollIntoView = vi.spyOn(Element.prototype, "scrollIntoView");
    const props = elicitationProps();
    const messages = [makeMessage()];
    const { rerender } = render(
      <MessageList messages={messages} isSending={false} {...props} />,
    );

    scrollIntoView.mockClear();
    rerender(<MessageList messages={messages} isSending {...props} />);

    expect(scrollIntoView).toHaveBeenCalledOnce();
  });

  it("renders the log with no bubbles when there are no messages", () => {
    render(
      <MessageList messages={[]} isSending={false} {...elicitationProps()} />,
    );

    const log = screen.getByRole("log", { name: "Conversation" });
    expect(log).toBeInTheDocument();
    expect(log.textContent).toBe("");
  });
});
