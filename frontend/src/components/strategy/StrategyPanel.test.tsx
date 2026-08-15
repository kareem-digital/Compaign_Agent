import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { StrategyPanel } from "@/components/strategy/StrategyPanel";
import { makeForecast, makePlan } from "@/test/factories";

describe("StrategyPanel", () => {
  it("names itself as a landmark and reports the plan's status and progress", () => {
    render(<StrategyPanel plan={makePlan()} />);

    const panel = screen.getByRole("complementary", { name: "Strategy plan" });
    expect(panel).toBeInTheDocument();
    expect(within(panel).getByText("Draft")).toBeInTheDocument();
    expect(within(panel).getByText("15% complete")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveValue(15);
  });

  it("lists the open stages and the locked ones separately", () => {
    render(<StrategyPanel plan={makePlan()} />);

    const stages = screen.getByRole("list", { name: "Plan stages" });
    expect(within(stages).getByText("Basic details")).toBeInTheDocument();
    expect(within(stages).getByText("Goals, KPI & bid")).toBeInTheDocument();

    const locked = screen.getByRole("list", {
      name: "Stages that unlock after approval",
    });
    expect(within(locked).getByText("Creatives")).toBeInTheDocument();
    expect(screen.getByText("Unlocks after approval")).toBeInTheDocument();
  });

  it("omits the locked section when nothing is gated", () => {
    render(<StrategyPanel plan={makePlan({ lockedStages: [] })} />);

    expect(screen.queryByText("Unlocks after approval")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("list", { name: "Stages that unlock after approval" }),
    ).not.toBeInTheDocument();
  });

  it("opens on the stage the plan marks open", () => {
    render(<StrategyPanel plan={makePlan()} />);

    expect(screen.getByRole("button", { name: /Basic details/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByText("Mega Toothpaste")).toBeInTheDocument();
  });

  it("keeps one stage open at a time", async () => {
    const user = userEvent.setup();
    render(<StrategyPanel plan={makePlan()} />);

    await user.click(screen.getByRole("button", { name: /Goals, KPI & bid/ }));

    expect(screen.getByRole("button", { name: /Basic details/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByRole("button", { name: /Goals, KPI & bid/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    // The previously open stage's body went with it.
    expect(screen.queryByText("Mega Toothpaste")).not.toBeInTheDocument();
  });

  it("closes the open stage when its own header is clicked again", async () => {
    const user = userEvent.setup();
    render(<StrategyPanel plan={makePlan()} />);

    await user.click(screen.getByRole("button", { name: /Basic details/ }));

    expect(screen.getByRole("button", { name: /Basic details/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByText("Mega Toothpaste")).not.toBeInTheDocument();
  });

  it("starts with every stage closed when the plan marks none open", () => {
    const plan = makePlan();
    render(
      <StrategyPanel
        plan={{
          ...plan,
          stages: plan.stages.map((stage) => ({ ...stage, isOpen: false })),
        }}
      />,
    );

    expect(screen.queryByText("Mega Toothpaste")).not.toBeInTheDocument();
  });

  it("keeps Accept Plan out of reach until the plan is complete", () => {
    const { rerender } = render(<StrategyPanel plan={makePlan()} />);

    expect(screen.getByRole("button", { name: "Accept Plan" })).toBeDisabled();

    rerender(<StrategyPanel plan={makePlan({ completion: 100 })} />);

    expect(screen.getByRole("button", { name: "Accept Plan" })).toBeEnabled();
  });

  it("switches to Launch strategy and mutes the curve once approved", () => {
    render(
      <StrategyPanel
        plan={makePlan({
          status: "approved",
          completion: 100,
          forecast: makeForecast(),
        })}
      />,
    );

    expect(screen.getByRole("button", { name: "Launch strategy" })).toBeEnabled();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    // Muted, so the live-figure tag is gone.
    expect(screen.queryByText("Generated")).not.toBeInTheDocument();
  });

  it("docks the forecast so it cannot scroll out of view", () => {
    render(<StrategyPanel plan={makePlan({ forecast: makeForecast() })} />);

    // The figure the Accept Plan decision is made against sits outside the
    // scroll region, alongside the button.
    const chart = screen.getByRole("img", { name: /Unique reach against Budget/ });
    const scrollRegion = document.querySelector(".overflow-y-auto");
    expect(scrollRegion?.contains(chart)).toBe(false);
  });
});
