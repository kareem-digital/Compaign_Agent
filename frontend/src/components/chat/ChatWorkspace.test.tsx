import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatWorkspace } from "@/components/chat/ChatWorkspace";
import { textBlock } from "@/lib/chat";
import { makeMessage, makeOptionsBlock, makePlan } from "@/test/factories";

function renderWorkspace(
  overrides: Partial<React.ComponentProps<typeof ChatWorkspace>> = {},
) {
  const onSend = vi.fn();
  const onAnswer = vi.fn();
  const result = render(
    <ChatWorkspace
      plan={makePlan()}
      messages={[makeMessage({ content: [textBlock("first")] })]}
      isSending={false}
      error={null}
      activeElicitation={null}
      submissions={{}}
      onSend={onSend}
      onAnswer={onAnswer}
      {...overrides}
    />,
  );
  return { onSend, onAnswer, ...result };
}

describe("ChatWorkspace", () => {
  it("frames the transcript with the plan's title bar and the disclaimer", () => {
    renderWorkspace();

    expect(
      screen.getByRole("heading", { level: 1, name: "New strategy" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByRole("log", { name: "Conversation" })).toBeInTheDocument();
    expect(screen.getByText("first")).toBeInTheDocument();
    expect(
      screen.getByText(
        "VOW Agent can make mistakes. Review important campaign details.",
      ),
    ).toBeInTheDocument();
  });

  it("sends a typed turn as a new message when no question is open", async () => {
    const user = userEvent.setup();
    const { onSend, onAnswer } = renderWorkspace();

    await user.type(
      screen.getByLabelText("Message VOW Agent"),
      "Plan a CTV campaign{Enter}",
    );

    expect(onSend).toHaveBeenCalledWith("Plan a CTV campaign");
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("routes the composer to the open question when it invites a typed answer", async () => {
    // While a question allows custom text the composer *is* its "something
    // else" field, so the text has to stay tied to the elicitation on the wire.
    const user = userEvent.setup();
    const activeElicitation = makeOptionsBlock({ allowCustom: true });
    const { onSend, onAnswer } = renderWorkspace({ activeElicitation });

    await user.type(
      screen.getByLabelText("Message VOW Agent"),
      "Connected TV only{Enter}",
    );

    expect(onAnswer).toHaveBeenCalledWith(activeElicitation, {
      optionIds: [],
      customText: "Connected TV only",
    });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("still sends a plain turn when the open question takes no typed answer", async () => {
    const user = userEvent.setup();
    const { onSend, onAnswer } = renderWorkspace({
      activeElicitation: makeOptionsBlock({ allowCustom: false }),
    });

    await user.type(
      screen.getByLabelText("Message VOW Agent"),
      "unrelated{Enter}",
    );

    expect(onSend).toHaveBeenCalledWith("unrelated");
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("re-prompts the composer while a typed answer is invited", () => {
    const { rerender } = renderWorkspace();
    expect(
      screen.getByPlaceholderText("Describe the campaign you want to plan…"),
    ).toBeInTheDocument();

    rerender(
      <ChatWorkspace
        plan={makePlan()}
        messages={[]}
        isSending={false}
        error={null}
        activeElicitation={makeOptionsBlock({ allowCustom: true })}
        submissions={{}}
        onSend={vi.fn()}
        onAnswer={vi.fn()}
      />,
    );

    expect(
      screen.getByPlaceholderText("Answer in your own words…"),
    ).toBeInTheDocument();
  });

  it("surfaces an error as an alert and renders none otherwise", () => {
    const { rerender } = renderWorkspace();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    rerender(
      <ChatWorkspace
        plan={makePlan()}
        messages={[]}
        isSending={false}
        error="The agent could not be reached."
        activeElicitation={null}
        submissions={{}}
        onSend={vi.fn()}
        onAnswer={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "The agent could not be reached.",
    );
  });

  it("locks the composer and shows the indicator while a reply is in flight", () => {
    renderWorkspace({ isSending: true });

    expect(screen.getByLabelText("Message VOW Agent")).toBeDisabled();
    expect(screen.getByLabelText("VOW Agent is typing")).toBeInTheDocument();
  });

  it("hands the active question's id down to the transcript", () => {
    const block = makeOptionsBlock();
    renderWorkspace({
      messages: [makeMessage({ role: "assistant", content: [block] })],
      activeElicitation: block,
    });

    // Interactive, so the rows are buttons rather than static text.
    expect(
      screen.getByRole("button", { name: /Prime Video/ }),
    ).toBeInTheDocument();
  });

  it("appends a caller's className", () => {
    const { container } = renderWorkspace({ className: "border-e" });

    expect(container.firstElementChild).toHaveClass("border-e");
  });
});
