import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatInput } from "@/components/chat/ChatInput";
import { chatLimits } from "@/lib/config";

const getTextarea = () => screen.getByLabelText("Message VOW Agent");
const getSendButton = () => screen.getByRole("button", { name: "Send message" });

describe("ChatInput", () => {
  it("keeps send disabled until there is non-whitespace input", async () => {
    const user = userEvent.setup();
    render(<ChatInput onSend={vi.fn()} />);

    expect(getSendButton()).toBeDisabled();

    await user.type(getTextarea(), "   ");
    expect(getSendButton()).toBeDisabled();

    await user.type(getTextarea(), "brief");
    expect(getSendButton()).toBeEnabled();
  });

  it("submits on Enter and clears the composer", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} />);

    await user.type(getTextarea(), "Plan a CTV campaign{Enter}");

    expect(onSend).toHaveBeenCalledExactlyOnceWith("Plan a CTV campaign");
    expect(getTextarea()).toHaveValue("");
  });

  it("inserts a newline on Shift+Enter instead of submitting", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} />);

    await user.type(getTextarea(), "line one{Shift>}{Enter}{/Shift}line two");

    expect(onSend).not.toHaveBeenCalled();
    expect(getTextarea()).toHaveValue("line one\nline two");
  });

  it("does not submit while disabled", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput value="a ready brief" onSend={onSend} disabled />);

    expect(getTextarea()).toBeDisabled();
    await user.click(getSendButton());

    expect(onSend).not.toHaveBeenCalled();
  });

  it("reports changes upward when controlled", async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    render(<ChatInput value="" onValueChange={onValueChange} onSend={vi.fn()} />);

    await user.type(getTextarea(), "x");

    expect(onValueChange).toHaveBeenCalledWith("x");
  });

  it("submits when the send button is clicked", async () => {
    // The button is type=submit, so this goes through the form's onSubmit
    // rather than the keydown path the Enter test covers.
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} />);

    await user.type(getTextarea(), "Plan a CTV campaign");
    await user.click(getSendButton());

    expect(onSend).toHaveBeenCalledExactlyOnceWith("Plan a CTV campaign");
    expect(getTextarea()).toHaveValue("");
  });

  it("hides the character counter until the limit is close", () => {
    render(<ChatInput value="short" onSend={vi.fn()} />);

    expect(screen.queryByText(/characters left/)).not.toBeInTheDocument();
  });

  it("counts down the remaining characters as the limit approaches", () => {
    render(
      <ChatInput value={"x".repeat(chatLimits.maxMessageLength - 40)} onSend={vi.fn()} />,
    );

    expect(screen.getByText("40 characters left")).toBeInTheDocument();
  });

  it("flags the counter once the limit is used up", () => {
    render(
      <ChatInput value={"x".repeat(chatLimits.maxMessageLength)} onSend={vi.fn()} />,
    );

    expect(screen.getByText("0 characters left")).toHaveClass("text-error");
  });
});
