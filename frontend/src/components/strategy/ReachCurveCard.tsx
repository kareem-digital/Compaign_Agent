import { Expand, TrendUp } from "@/components/icons";
import { ReachCurveChart } from "@/components/strategy/ReachCurveChart";
import { cn } from "@/lib/utils";
import type { ReachForecast } from "@/types/strategy";

const COPY = {
  title: "Reach curve",
  generated: "Generated",
  notYet: "Not yet",
  pending:
    "Generates once basic details, goals, inventory and targeting are set.",
  expand: "Open the reach curve full frame",
  series: "Cumulative unique reach",
  ceiling: "Addressable ceiling",
} as const;

interface ReachCurveCardProps {
  /** `null` is the resting state: the curve has no inputs yet. */
  forecast: ReachForecast | null;
  isMuted?: boolean;
  onExpand?: () => void;
  className?: string;
}

/**
 * The panel's docked forecast. It is the one part of the plan that carries real
 * numbers, so the chart itself is a separate component and this owns only the
 * chrome around it — status, the four headline stats, the legend.
 */
export function ReachCurveCard({
  forecast,
  isMuted = false,
  onExpand,
  className,
}: ReachCurveCardProps) {
  if (!forecast) {
    return (
      <section
        className={cn(
          "card card-border rounded-field border-base-300/50 bg-base-100",
          className,
        )}
      >
        <div className="card-body gap-2 p-4">
          <div className="flex items-center gap-2.5">
            <h2 className="flex-1 text-card-title font-bold text-base-content/60">
              {COPY.title}
            </h2>
            <span className="badge badge-soft badge-neutral badge-sm rounded-full border-none text-micro font-bold uppercase">
              {COPY.notYet}
            </span>
          </div>
          <p className="text-note text-base-content/50">{COPY.pending}</p>
        </div>
      </section>
    );
  }

  return (
    <section className={cn("flex flex-col gap-2.5", className)}>
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "grid size-5.5 flex-none place-items-center rounded-full",
            isMuted ? "bg-base-content/30" : "bg-accent",
          )}
        >
          <TrendUp className="size-3 text-base-100" />
        </span>
        <h2 className="text-card-title font-bold text-base-content">
          {COPY.title}
        </h2>
        {!isMuted && (
          <span className="badge badge-soft badge-accent badge-sm rounded-full border-none text-micro font-bold uppercase">
            {COPY.generated}
          </span>
        )}
        <span className="flex-1" />
        {onExpand && (
          <button
            type="button"
            aria-label={COPY.expand}
            onClick={onExpand}
            className="btn btn-square btn-ghost btn-xs rounded-selector border border-base-300/60 bg-base-100 text-primary"
          >
            <Expand className="size-3.5" />
          </button>
        )}
      </div>

      <dl className="flex gap-4">
        {forecast.stats.map(({ label, value }, index) => (
          <div key={label} className="flex items-center gap-4">
            {index > 0 && <span className="h-8 w-px bg-base-300/60" />}
            <div className="flex flex-col gap-1">
              <dt className="text-micro font-semibold uppercase tracking-label text-base-content/50">
                {label}
              </dt>
              <dd
                className={cn(
                  "text-xl font-extrabold",
                  isMuted ? "text-base-content/60" : "text-base-content",
                )}
              >
                {value}
              </dd>
            </div>
          </div>
        ))}
      </dl>

      <div className="rounded-selector border border-base-300/50 bg-base-100 px-3 pt-2.5 pb-1.5">
        <ReachCurveChart
          curve={forecast.curve}
          ceiling={forecast.ceiling}
          ceilingLabel={forecast.ceilingLabel}
          peakLabel={forecast.peakLabel}
          axisLabels={forecast.axisLabels}
          xTicks={forecast.xTicks}
          yTicks={forecast.yTicks}
          isMuted={isMuted}
        />
        <div className="flex items-center gap-3.5 pt-0.5">
          <span className="flex items-center gap-1.5 text-micro text-base-content/70">
            <span
              className={cn(
                "h-0.5 w-3.5",
                isMuted ? "bg-base-content/50" : "bg-primary",
              )}
            />
            {COPY.series}
          </span>
          <span className="flex items-center gap-1.5 text-micro text-base-content/70">
            <span className="w-3.5 border-t-2 border-dashed border-accent/40" />
            {COPY.ceiling}
          </span>
          <span className="flex-1" />
          <span className="text-micro text-base-content/40">
            {forecast.updatedLabel}
          </span>
        </div>
      </div>
    </section>
  );
}
