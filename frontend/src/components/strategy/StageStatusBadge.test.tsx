import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StageStatusBadge } from "@/components/strategy/StageStatusBadge";
import type { StageStatus } from "@/types/strategy";

describe("StageStatusBadge", () => {
  it.each([
    ["in-progress", "In progress", "badge-accent"],
    ["complete", "Complete", "badge-success"],
    ["optional", "Optional", "badge-neutral"],
    ["needs-input", "Needs input", "badge-warning"],
  ] as const)("draws %s as a %s pill", (status, label, tone) => {
    render(<StageStatusBadge status={status} />);

    const badge = screen.getByText(label);
    expect(badge).toHaveClass("badge", tone);
  });

  it("draws `next` as bare text, not a pill", () => {
    // A hint about what follows, not a state the stage is in.
    render(<StageStatusBadge status="next" />);

    const label = screen.getByText("Next");
    expect(label).not.toHaveClass("badge");
  });

  it.each(["locked", "pending"] as const)("renders nothing for %s", (status) => {
    const { container } = render(<StageStatusBadge status={status} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("appends a caller's className", () => {
    render(<StageStatusBadge status="complete" className="ms-2" />);

    expect(screen.getByText("Complete")).toHaveClass("ms-2");
  });

  it("has a decision for every status in the union", () => {
    // Guards against a new StageStatus silently rendering an empty pill.
    const all: StageStatus[] = [
      "in-progress",
      "complete",
      "next",
      "optional",
      "needs-input",
      "locked",
      "pending",
    ];

    for (const status of all) {
      expect(() => render(<StageStatusBadge status={status} />)).not.toThrow();
    }
  });
});
