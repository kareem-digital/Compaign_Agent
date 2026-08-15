import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkspaceHeader } from "@/components/layout/WorkspaceHeader";

describe("WorkspaceHeader", () => {
  it("names the open strategy as the workspace heading", () => {
    render(<WorkspaceHeader name="New strategy" status="draft" />);

    expect(
      screen.getByRole("heading", { level: 1, name: "New strategy" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });

  it.each([
    ["draft", "Draft", "badge-accent"],
    ["approved", "Approved", "badge-success"],
    ["launched", "Launched", "badge-primary"],
  ] as const)("tags a %s plan", (status, label, tone) => {
    render(<WorkspaceHeader name="New strategy" status={status} />);

    expect(screen.getByText(label)).toHaveClass("badge", tone);
  });

  it("appends a caller's className without dropping its own layout", () => {
    render(
      <WorkspaceHeader name="New strategy" status="draft" className="sticky" />,
    );

    const header = screen.getByRole("banner");
    expect(header).toHaveClass("sticky");
    expect(header).toHaveClass("flex-none");
  });
});
