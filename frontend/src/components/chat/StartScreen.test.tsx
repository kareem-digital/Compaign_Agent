import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StartScreen } from "@/components/chat/StartScreen";

const props = { isSending: false, error: null, onSend: vi.fn() };

describe("StartScreen", () => {
  it("leads with the brand mark, the title and the lede", () => {
    const { container } = render(<StartScreen {...props} />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Start planning" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Describe your objective or attach a brief/))
      .toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("sends what the user types and clears the composer", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<StartScreen {...props} onSend={onSend} />);

    const composer = screen.getByLabelText("Message VOW Agent");
    await user.type(composer, "Plan a CTV campaign{Enter}");

    expect(onSend).toHaveBeenCalledWith("Plan a CTV campaign");
    expect(composer).toHaveValue("");
  });

  it("drops a suggested start into the composer rather than sending it", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<StartScreen {...props} onSend={onSend} />);

    await user.click(
      screen.getByRole("button", { name: "Plan a Prime Video campaign" }),
    );

    // The chip prefills so the user can edit before committing.
    expect(screen.getByLabelText("Message VOW Agent")).toHaveValue(
      "Plan a Prime Video CTV campaign for an upcoming product launch.",
    );
    expect(onSend).not.toHaveBeenCalled();
  });

  it("offers every suggested start under one heading", () => {
    render(<StartScreen {...props} />);

    expect(
      screen.getByRole("heading", { level: 2, name: "Suggested starts" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("list")).toBeInTheDocument();
    for (const label of [
      "Upload campaign brief",
      "Plan a Prime Video campaign",
      "Start with a fixed budget",
      "Structure an incomplete brief",
    ]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("surfaces a transport error as an alert", () => {
    render(<StartScreen {...props} error="The agent could not be reached." />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "The agent could not be reached.",
    );
  });

  it("renders no alert region when there is nothing wrong", () => {
    render(<StartScreen {...props} />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("locks the composer and the chips while a reply is in flight", () => {
    render(<StartScreen {...props} isSending />);

    expect(screen.getByLabelText("Message VOW Agent")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Upload campaign brief" }),
    ).toBeDisabled();
  });

  it("appends a caller's className", () => {
    const { container } = render(<StartScreen {...props} className="pt-0" />);

    expect(container.firstElementChild).toHaveClass("pt-0");
  });
});
