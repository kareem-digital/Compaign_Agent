import { cn } from "@/lib/utils";
import type { ReachPoint } from "@/types/strategy";

/* Plot geometry, in the SVG's own user units — not design tokens, so they stay
 * here rather than in `tokens.css`. The viewBox is the design's; everything
 * inside is derived from these four edges. */
const VIEW = { width: 402, height: 158 };
const PLOT = { left: 50, right: 392, top: 12, bottom: 116 };
const AXIS_Y = { x: 11, y: 78 };
const TICK_Y = 130;
const LABEL_Y = 147;

const toX = (x: number) => PLOT.left + x * (PLOT.right - PLOT.left);
const toY = (y: number) => PLOT.bottom - y * (PLOT.bottom - PLOT.top);

/** Catmull-Rom through every point, converted to cubic béziers — the design's
 *  curve is smooth, and interpolating keeps the data honest at each sample. */
function toPath(points: ReachPoint[]): string {
  if (points.length < 2) return "";
  const pts = points.map(({ x, y }) => ({ x: toX(x), y: toY(y) }));
  let d = `M${pts[0].x} ${pts[0].y}`;
  for (let i = 0; i < pts.length - 1; i += 1) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    d +=
      `C${p1.x + (p2.x - p0.x) / 6} ${p1.y + (p2.y - p0.y) / 6}` +
      ` ${p2.x - (p3.x - p1.x) / 6} ${p2.y - (p3.y - p1.y) / 6}` +
      ` ${p2.x} ${p2.y}`;
  }
  return d;
}

interface ReachCurveChartProps {
  curve: ReachPoint[];
  /** Fraction of the y-axis the addressable ceiling sits at. */
  ceiling: number;
  ceilingLabel: string;
  peakLabel: string;
  axisLabels: { x: string; y: string };
  xTicks: string[];
  /** Bottom-to-top, matching the axis. */
  yTicks: string[];
  /** Muted once the plan is approved — the curve stops being the live figure. */
  isMuted?: boolean;
  className?: string;
}

export function ReachCurveChart({
  curve,
  ceiling,
  ceilingLabel,
  peakLabel,
  axisLabels,
  xTicks,
  yTicks,
  isMuted = false,
  className,
}: ReachCurveChartProps) {
  const line = toPath(curve);
  const peak = curve.at(-1);
  const ceilingY = toY(ceiling);
  const accent = isMuted ? "text-base-content/50" : "text-primary";

  return (
    <svg
      viewBox={`0 0 ${VIEW.width} ${VIEW.height}`}
      fill="none"
      role="img"
      aria-label={`${axisLabels.y} against ${axisLabels.x}. ${peakLabel} at the planned budget, against a ${ceilingLabel}.`}
      className={cn("block h-auto w-full", className)}
    >
      <text
        transform={`translate(${AXIS_Y.x} ${AXIS_Y.y}) rotate(-90)`}
        textAnchor="middle"
        className="fill-base-content/50 text-micro font-bold uppercase tracking-label"
      >
        {axisLabels.y}
      </text>

      {yTicks.map((tick, index) => (
        <text
          key={tick}
          x={PLOT.left - 6}
          y={toY(index / (yTicks.length - 1)) + 4}
          textAnchor="end"
          className="fill-base-content/50 text-micro font-semibold"
        >
          {tick}
        </text>
      ))}

      {yTicks.slice(1, -1).map((tick, index) => (
        <line
          key={tick}
          x1={PLOT.left}
          x2={PLOT.right}
          y1={toY((index + 1) / (yTicks.length - 1))}
          y2={toY((index + 1) / (yTicks.length - 1))}
          className="stroke-base-300/40"
        />
      ))}

      <line
        x1={PLOT.left}
        y1={PLOT.bottom}
        x2={PLOT.right}
        y2={PLOT.bottom}
        className="stroke-base-300"
      />
      <line
        x1={PLOT.left}
        y1={PLOT.top}
        x2={PLOT.left}
        y2={PLOT.bottom}
        className="stroke-base-300"
      />

      <line
        x1={PLOT.left}
        y1={ceilingY}
        x2={PLOT.right}
        y2={ceilingY}
        strokeDasharray="4 4"
        className="stroke-accent/40"
      />
      <text
        x={PLOT.left + 6}
        y={ceilingY + 12}
        className="fill-base-content/50 text-micro font-semibold"
      >
        {ceilingLabel}
      </text>

      {peak && (
        <>
          <path
            d={`${line}L${toX(peak.x)} ${PLOT.bottom}L${PLOT.left} ${PLOT.bottom}Z`}
            fillOpacity={0.07}
            className={cn("fill-current", accent)}
          />
          <path
            d={line}
            strokeWidth={2}
            strokeLinecap="round"
            className={cn("stroke-current", accent)}
          />
          <circle
            cx={toX(peak.x)}
            cy={toY(peak.y)}
            r={3.5}
            strokeWidth={2}
            className={cn("fill-base-100 stroke-current", accent)}
          />
          <text
            x={toX(peak.x) - 6}
            y={toY(peak.y) - 6}
            textAnchor="end"
            className={cn("fill-current text-micro font-bold", accent)}
          >
            {peakLabel}
          </text>
        </>
      )}

      {xTicks.map((tick, index) => (
        <text
          key={tick}
          x={toX(index / (xTicks.length - 1))}
          y={TICK_Y}
          textAnchor="middle"
          className="fill-base-content/50 text-micro"
        >
          {tick}
        </text>
      ))}
      <text
        x={(PLOT.left + PLOT.right) / 2}
        y={LABEL_Y}
        textAnchor="middle"
        className="fill-base-content/50 text-micro font-bold uppercase tracking-label"
      >
        {axisLabels.x}
      </text>
    </svg>
  );
}
