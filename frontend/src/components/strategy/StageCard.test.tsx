import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StageCard } from "@/components/strategy/StageCard";
import type { PlanStage } from "@/types/strategy";

const stage: PlanStage = {
  id: "basic-details",
  title: "Basic details",
  status: "in-progress",
};

/** The card is an `<li>`, so it needs a list parent to be valid markup. */
const inList = (ui: React.ReactNode) => render(<ul>{ui}</ul>);

describe("StageCard", () => {
  it("renders the title and its status tag", () => {
    inList(<StageCard stage={stage} onToggle={vi.fn()} />);

    expect(screen.getByText("Basic details")).toBeInTheDocument();
    expect(screen.getByText("In progress")).toBeInTheDocument();
  });

  it("reports its expanded state and toggles by id", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    inList(
      <StageCard stage={{ ...stage, isOpen: true }} onToggle={onToggle}>
        <p>Brand</p>
      </StageCard>,
    );

    const header = screen.getByRole("button", { name: /Basic details/ });
    expect(header).toHaveAttribute("aria-expanded", "true");

    await user.click(header);

    expect(onToggle).toHaveBeenCalledWith("basic-details");
  });

  it("shows its body only while open, and points the header at it", () => {
    const { rerender } = inList(
      <StageCard stage={{ ...stage, isOpen: true }} onToggle={vi.fn()}>
        <p>Brand</p>
      </StageCard>,
    );

    const body = screen.getByText("Brand").parentElement;
    expect(screen.getByRole("button", { name: /Basic details/ })).toHaveAttribute(
      "aria-controls",
      body?.id,
    );

    rerender(
      <ul>
        <StageCard stage={{ ...stage, isOpen: false }} onToggle={vi.fn()}>
          <p>Brand</p>
        </StageCard>
      </ul>,
    );

    expect(screen.queryByText("Brand")).not.toBeInTheDocument();
  });

  it("claims no body to control when it has no children", () => {
    inList(<StageCard stage={{ ...stage, isOpen: true }} onToggle={vi.fn()} />);

    expect(
      screen.getByRole("button", { name: /Basic details/ }),
    ).not.toHaveAttribute("aria-controls");
  });

  it("renders a locked stage as a dashed, unclickable frame with no tag", () => {
    const { container } = inList(
      <StageCard stage={{ ...stage, status: "locked" }} onToggle={vi.fn()} />,
    );

    // Inert even when handed a toggle: locked outranks it.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText("In progress")).not.toBeInTheDocument();
    expect(container.querySelector("li")).toHaveClass("border-dashed");
  });

  it("still renders a body if a locked stage is handed one", () => {
    // Documents an unenforced invariant rather than asserting the docblock:
    // "never renders a body" holds only because StrategyPanel passes locked
    // cards no children. The body render is gated on `isOpen && children`,
    // with no `isLocked` guard — see the note in the review summary.
    inList(
      <StageCard stage={{ ...stage, status: "locked", isOpen: true }}>
        <p>Brand</p>
      </StageCard>,
    );

    expect(screen.getByText("Brand")).toBeInTheDocument();
  });

  it("stays inert when no toggle handler is supplied", () => {
    inList(<StageCard stage={stage} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("Basic details")).toBeInTheDocument();
  });

  it("renders a trailing hint when the plan supplies one", () => {
    inList(
      <StageCard
        stage={{ ...stage, status: "locked", hint: "Once approved" }}
      />,
    );

    expect(screen.getByText("Once approved")).toBeInTheDocument();
  });
});
