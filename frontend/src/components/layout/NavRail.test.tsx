import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NavRail } from "@/components/layout/NavRail";

describe("NavRail", () => {
  it("is a named navigation landmark", () => {
    render(<NavRail />);

    expect(
      screen.getByRole("navigation", { name: "VOW Agent" }),
    ).toBeInTheDocument();
  });

  it("gives every icon control an accessible name", () => {
    // The controls are icon-only, so the label is the only thing naming them.
    render(<NavRail />);

    expect(
      screen.getByRole("button", { name: "New strategy" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Recent strategies" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("hides the decorative brand glyph from assistive technology", () => {
    const { container } = render(<NavRail />);

    expect(container.querySelector("[aria-hidden]")?.textContent).toBe("»");
  });

  it("appends a caller's className without dropping its own layout", () => {
    render(<NavRail className="hidden" />);

    const rail = screen.getByRole("navigation", { name: "VOW Agent" });
    expect(rail).toHaveClass("hidden");
    expect(rail).toHaveClass("flex-none");
  });
});
