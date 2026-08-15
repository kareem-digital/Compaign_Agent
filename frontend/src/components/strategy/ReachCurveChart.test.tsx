import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReachCurveChart } from "@/components/strategy/ReachCurveChart";
import { makeForecast } from "@/test/factories";

const forecast = makeForecast();

const chartProps = {
  curve: forecast.curve,
  ceiling: forecast.ceiling,
  ceilingLabel: forecast.ceilingLabel,
  peakLabel: forecast.peakLabel,
  axisLabels: forecast.axisLabels,
  xTicks: forecast.xTicks,
  yTicks: forecast.yTicks,
};

describe("ReachCurveChart", () => {
  it("describes itself to assistive technology in place of the plot", () => {
    render(<ReachCurveChart {...chartProps} />);

    expect(
      screen.getByRole("img", {
        name: "Unique reach against Budget. ~2.4M at the planned budget, against a Addressable audience 3.5M.",
      }),
    ).toBeInTheDocument();
  });

  it("labels both axes and every tick", () => {
    render(<ReachCurveChart {...chartProps} />);

    expect(screen.getByText("Budget")).toBeInTheDocument();
    expect(screen.getByText("Unique reach")).toBeInTheDocument();
    for (const tick of [...forecast.xTicks, ...forecast.yTicks]) {
      expect(screen.getByText(tick)).toBeInTheDocument();
    }
  });

  it("draws the series as a smooth path through every sample", () => {
    const { container } = render(<ReachCurveChart {...chartProps} />);

    const line = [...container.querySelectorAll("path")].find((path) =>
      path.getAttribute("class")?.includes("stroke-current"),
    );
    const d = line?.getAttribute("d") ?? "";

    expect(d.startsWith("M")).toBe(true);
    // One cubic segment per gap between samples.
    expect(d.match(/C/g)).toHaveLength(forecast.curve.length - 1);
  });

  it("marks the peak and the addressable ceiling", () => {
    const { container } = render(<ReachCurveChart {...chartProps} />);

    expect(screen.getByText("~2.4M")).toBeInTheDocument();
    expect(screen.getByText("Addressable audience 3.5M")).toBeInTheDocument();
    expect(container.querySelector("circle")).not.toBeNull();
    expect(
      container.querySelector('line[stroke-dasharray="4 4"]'),
    ).not.toBeNull();
  });

  it("omits the series entirely when there is no curve to draw", () => {
    const { container } = render(
      <ReachCurveChart {...chartProps} curve={[]} />,
    );

    // Axes and ticks still render; the peak marker and its label do not.
    expect(screen.queryByText("~2.4M")).not.toBeInTheDocument();
    expect(container.querySelector("circle")).toBeNull();
    expect(screen.getByText("Budget")).toBeInTheDocument();
  });

  it("mutes the series once the plan is approved", () => {
    const { container, rerender } = render(
      <ReachCurveChart {...chartProps} />,
    );
    const seriesClass = () =>
      [...container.querySelectorAll("path")]
        .map((p) => p.getAttribute("class") ?? "")
        .join(" ");

    expect(seriesClass()).toContain("text-primary");

    rerender(<ReachCurveChart {...chartProps} isMuted />);

    expect(seriesClass()).not.toContain("text-primary");
  });

  it("scales the ceiling line with the fraction it is given", () => {
    const { container: full } = render(
      <ReachCurveChart {...chartProps} ceiling={1} />,
    );
    const { container: half } = render(
      <ReachCurveChart {...chartProps} ceiling={0.5} />,
    );

    const yOf = (root: HTMLElement) =>
      root
        .querySelector('line[stroke-dasharray="4 4"]')
        ?.getAttribute("y1");

    // A lower ceiling sits further down the plot, so its y grows.
    expect(Number(yOf(half))).toBeGreaterThan(Number(yOf(full)));
  });
});
