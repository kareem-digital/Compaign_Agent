import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TypingIndicator } from "@/components/chat/TypingIndicator";

describe("TypingIndicator", () => {
  it("announces itself politely while the agent is composing", () => {
    render(<TypingIndicator />);

    const indicator = screen.getByLabelText("VOW Agent is typing");
    expect(indicator).toHaveAttribute("aria-live", "polite");
  });

  it("gives screen readers words rather than the decorative dots", () => {
    const { container } = render(<TypingIndicator />);

    expect(screen.getByText("Thinking…")).toHaveClass("sr-only");
    expect(container.querySelector(".loading-dots")).not.toBeNull();
  });

  it("matches the agent turn's layout so the reply lands where the dots were", () => {
    const { container } = render(<TypingIndicator />);

    // Same brand mark and gap as MessageBubble's assistant branch.
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.firstElementChild).toHaveClass("flex", "gap-3");
  });
});
