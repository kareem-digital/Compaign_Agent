import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ReachCurveCard } from "@/components/strategy/ReachCurveCard";
import { makeForecast } from "@/test/factories";

describe("ReachCurveCard", () => {
  it("rests as a pending card when the curve has no inputs yet", () => {
    render(<ReachCurveCard forecast={null} />);

    expect(screen.getByText("Reach curve")).toBeInTheDocument();
    expect(screen.getByText("Not yet")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Generates once basic details, goals, inventory and targeting are set.",
      ),
    ).toBeInTheDocument();
    // No chart to describe, so no image role either.
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders the headline stats, the chart and the legend once generated", () => {
    const forecast = makeForecast();
    render(<ReachCurveCard forecast={forecast} />);

    expect(screen.getByText("Generated")).toBeInTheDocument();
    expect(screen.getByText("Unique reach", { selector: "dt" }))
      .toBeInTheDocument();
    expect(screen.getByText("~2.4M", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("3.2×")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Unique reach against Budget/ }))
      .toBeInTheDocument();
    expect(screen.getByText("Cumulative unique reach")).toBeInTheDocument();
    expect(screen.getByText("Addressable ceiling")).toBeInTheDocument();
    expect(screen.getByText("Updated just now")).toBeInTheDocument();
  });

  it("drops the generated tag once the plan is approved", () => {
    render(<ReachCurveCard forecast={makeForecast()} isMuted />);

    // Muted: the curve is no longer the live figure.
    expect(screen.queryByText("Generated")).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Unique reach/ })).toBeInTheDocument();
  });

  it("offers a full-frame control only when the host can handle it", async () => {
    const user = userEvent.setup();
    const onExpand = vi.fn();
    const { rerender } = render(
      <ReachCurveCard forecast={makeForecast()} onExpand={onExpand} />,
    );

    await user.click(
      screen.getByRole("button", { name: "Open the reach curve full frame" }),
    );
    expect(onExpand).toHaveBeenCalledOnce();

    rerender(<ReachCurveCard forecast={makeForecast()} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders a divider between stats but not before the first", () => {
    const { container } = render(
      <ReachCurveCard forecast={makeForecast()} />,
    );

    // Two stats, so exactly one separator.
    expect(container.querySelectorAll(".w-px")).toHaveLength(1);
  });
});
