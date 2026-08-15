import { useState } from "react";

import { PropertyRows } from "@/components/strategy/PropertyRows";
import { ReachCurveCard } from "@/components/strategy/ReachCurveCard";
import { StageCard } from "@/components/strategy/StageCard";
import { cn } from "@/lib/utils";
import type { PlanStatus, StrategyPlan } from "@/types/strategy";

const COPY = {
  title: "Strategy plan",
  progress: (percent: number) => `${percent}% complete`,
  unlocks: "Unlocks after approval",
  accept: "Accept Plan",
  launch: "Launch strategy",
  stages: "Plan stages",
  locked: "Stages that unlock after approval",
} as const;

const STATUS_COPY: Record<PlanStatus, string> = {
  draft: "Draft",
  approved: "Approved",
  launched: "Launched",
};

const STATUS_TONE: Record<PlanStatus, string> = {
  draft: "badge-accent",
  approved: "badge-success",
  launched: "badge-primary",
};

interface StrategyPanelProps {
  plan: StrategyPlan;
  className?: string;
}

/**
 * The inline-end plan panel: a fixed header, one scroll region of stacked stage
 * cards, and a dock that never scrolls. The reach curve stays in that dock in
 * every state — it is the figure the Accept Plan decision is made against, so
 * it must not be able to scroll out of view.
 */
export function StrategyPanel({ plan, className }: StrategyPanelProps) {
  const [openStageId, setOpenStageId] = useState(
    () => plan.stages.find((stage) => stage.isOpen)?.id ?? null,
  );

  const isApproved = plan.status !== "draft";

  return (
    <aside
      aria-label={COPY.title}
      className={cn(
        "flex w-(--container-strategy) flex-none flex-col overflow-hidden border-s border-base-300/60 bg-base-200",
        className,
      )}
    >
      <div className="flex h-(--workspace-header-height) flex-none items-center justify-between gap-2.5 border-b border-base-300/60 bg-base-100 px-5">
        <div className="flex items-center gap-2">
          <h2 className="text-card-title font-bold text-base-content">
            {COPY.title}
          </h2>
          <span
            className={cn(
              "badge badge-soft badge-sm rounded-full border-none text-micro font-bold uppercase",
              STATUS_TONE[plan.status],
            )}
          >
            {STATUS_COPY[plan.status]}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <progress
            className="progress progress-accent h-1.5 w-18"
            value={plan.completion}
            max={100}
          />
          <span className="text-note font-semibold text-base-content/60">
            {COPY.progress(plan.completion)}
          </span>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-5 pt-3.5 pb-1">
        <ul aria-label={COPY.stages} className="flex flex-col gap-2.5">
          {plan.stages.map((stage) => (
            <StageCard
              key={stage.id}
              stage={{ ...stage, isOpen: stage.id === openStageId }}
              onToggle={(id) =>
                setOpenStageId((current) => (current === id ? null : id))
              }
            >
              {stage.properties && <PropertyRows properties={stage.properties} />}
            </StageCard>
          ))}
        </ul>

        {plan.lockedStages.length > 0 && (
          <>
            <div className="flex items-center gap-2.5 pt-0.5">
              <span className="h-px flex-1 bg-base-300/60" />
              <span className="text-micro font-bold uppercase tracking-label text-base-content/50">
                {COPY.unlocks}
              </span>
              <span className="h-px flex-1 bg-base-300/60" />
            </div>
            <ul aria-label={COPY.locked} className="flex flex-col gap-2.5">
              {plan.lockedStages.map((stage) => (
                <StageCard key={stage.id} stage={stage} />
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="flex flex-none flex-col gap-2.5 border-t border-base-300/60 bg-base-100 px-5 pt-3.5 pb-4">
        <ReachCurveCard forecast={plan.forecast} isMuted={isApproved} />
        <button
          type="button"
          disabled={plan.completion < 100}
          className="btn btn-primary btn-block rounded-selector text-control font-bold"
        >
          {isApproved ? COPY.launch : COPY.accept}
        </button>
      </div>
    </aside>
  );
}
